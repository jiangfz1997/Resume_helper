<template>
  <div :class="stage === 'result' ? 'gen-fullscreen' : 'gen-centered'">

    <!-- Stage 1 header -->
    <template v-if="stage === 'jd'">
      <n-page-header title="Generate Resume" style="margin-bottom: 20px" />
      <n-steps :current="1" style="margin-bottom: 24px">
        <n-step title="Job Description" description="Paste the JD text" />
        <n-step title="Edit & Export" description="Refine and download" />
      </n-steps>
    </template>

    <!-- Stage 1: JD input -->
    <template v-if="stage === 'jd'">
      <n-card title="Job Description">
        <n-input
          v-model:value="jdText"
          type="textarea"
          :rows="12"
          placeholder="Paste the full job description here..."
          style="font-family: monospace; font-size: 13px"
        />
        <n-alert v-if="analyzeError" type="error" style="margin-top: 12px">{{ analyzeError }}</n-alert>
        <template #footer>
          <n-button type="primary" :loading="analyzeLoading" :disabled="!jdText.trim()" @click="runAnalyze">
            {{ analyzeLoading ? 'Analyzing & Generating...' : 'Analyze & Generate' }}
          </n-button>
        </template>
      </n-card>
    </template>

    <!-- Stage 2: Split editor + preview -->
    <template v-if="stage === 'result'">
      <!-- Top toolbar -->
      <div class="stage3-toolbar">
        <!-- Breadcrumb -->
        <div class="toolbar-breadcrumb">
          <span class="bc-done">Job Description</span>
          <span class="bc-sep">›</span>
          <span class="bc-active">Edit &amp; Export</span>
        </div>

        <div class="toolbar-divider" />

        <!-- Match score chip (available as soon as analyze completes) -->
        <n-tooltip v-if="preview" trigger="hover" placement="bottom">
          <template #trigger>
            <div class="score-chip" :class="scoreChipClass(matchPct)">
              <span class="sc-label">Match</span>
              <span class="sc-value">{{ matchPct }}%</span>
              <span class="sc-status">{{ scoreStatusText(matchPct) }}</span>
            </div>
          </template>
          Profile-to-JD semantic match score from skill matching
        </n-tooltip>

        <!-- Score chips (available after draft generated) -->
        <div class="toolbar-scores" v-if="kwDetail">
          <n-tooltip trigger="hover" placement="bottom">
            <template #trigger>
              <div class="score-chip" :class="scoreChipClass(reqPct)">
                <span class="sc-label">Qualifications</span>
                <span class="sc-value">{{ reqPct }}%</span>
                <span class="sc-status">{{ scoreStatusText(reqPct) }}</span>
              </div>
            </template>
            Coverage of explicitly required skills. Target ≥ 80%.
          </n-tooltip>

          <n-tooltip trigger="hover" placement="bottom">
            <template #trigger>
              <div class="score-chip" :class="scoreChipClass(kwPct)">
                <span class="sc-label">ATS Coverage</span>
                <span class="sc-value">{{ kwPct }}%</span>
                <span class="sc-status">{{ scoreStatusText(kwPct) }}</span>
              </div>
            </template>
            Literal keyword match simulating ATS scanners (required 1.0× + preferred 0.6× + nice-to-have 0.2×). Low score means the resume text is missing exact keyword strings — add them explicitly. Target ≥ 70%.
          </n-tooltip>
        </div>

        <!-- Issue summary -->
        <template v-if="!diagnoseLoading && diagnosticReport">
          <div class="toolbar-divider" />
          <div class="toolbar-issues" @click="leftActiveTab = 'copilot'">
            <template v-if="criticalCount > 0">
              <n-text style="font-size:12px;color:#d03050;font-weight:600">{{ criticalCount }} critical</n-text>
            </template>
            <template v-if="suggestionCount > 0">
              <n-text style="font-size:12px;color:#f0a020;margin-left:6px">{{ suggestionCount }} suggestions</n-text>
            </template>
            <template v-if="criticalCount === 0 && suggestionCount === 0">
              <n-text style="font-size:12px;color:#18a058">No issues</n-text>
            </template>
          </div>
        </template>
        <!-- Draft generating indicator -->
        <template v-if="draftLoading">
          <div class="toolbar-divider" />
          <n-spin size="small" />
          <n-text depth="3" style="font-size:12px">Generating draft...</n-text>
        </template>
        <n-spin v-else-if="diagnoseLoading" size="small" style="margin-left:8px" />

        <n-space align="center" size="small" style="margin-left: auto">
          <n-button size="small" quaternary @click="reset">Start Over</n-button>
          <n-button v-if="currentSessionId && !draftLoading" size="small" :loading="saveLoading" @click="saveDraft">Save</n-button>
        </n-space>
      </div>

      <!-- Left / Right split -->
      <div class="stage3-split">
        <!-- Left pane -->
        <div class="stage3-left" @mouseup="onLeftMouseUp">
          <n-tabs v-model:value="leftActiveTab" type="line" size="small" style="height: 100%; display: flex; flex-direction: column">
            <!-- Match tab (always shown once in result stage) -->
            <n-tab-pane name="match" style="flex:1;overflow-y:auto;padding:0">
              <template #tab>
                <n-space align="center" size="small" :wrap="false">
                  <span>Match</span>
                  <n-badge v-if="preview && preview.missing_skills.length" :value="preview.missing_skills.length" type="warning" />
                </n-space>
              </template>
              <div v-if="preview" style="padding:12px 8px">
                <!-- Profile Fit -->
                <n-card size="small" style="margin-bottom:12px;background:#1a1a1a">
                  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                    <n-text style="font-size:13px;font-weight:600">{{ preview.job_title }}</n-text>
                    <n-text depth="3" style="font-size:12px" v-if="preview.company">@ {{ preview.company }}</n-text>
                  </div>
                  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                    <n-tooltip trigger="hover">
                      <template #trigger>
                        <n-text style="font-size:12px;min-width:80px;color:#aaa;cursor:help">Profile Fit</n-text>
                      </template>
                      Semantic match between your background and the JD, assessed by AI. Based on your profile, not the generated resume.
                    </n-tooltip>
                    <n-progress
                      type="line"
                      :percentage="matchPct"
                      :color="matchPct >= 60 ? '#18a058' : '#f0a020'"
                      :rail-color="'#2a2a2a'"
                      style="flex:1"
                    />
                    <n-text :style="`font-size:13px;font-weight:700;color:${matchPct >= 60 ? '#18a058' : '#f0a020'}`">
                      {{ matchPct }}%
                    </n-text>
                  </div>
                  <n-blockquote v-if="preview.relevance_notes" style="margin-top:8px;font-size:12px">
                    {{ preview.relevance_notes }}
                  </n-blockquote>
                  <div style="margin-top:10px">
                    <n-text style="font-size:11px;color:#18a058;font-weight:600;text-transform:uppercase;letter-spacing:0.4px;display:block;margin-bottom:4px">Matched</n-text>
                    <n-space v-if="preview.matched_skills.length" size="small" style="flex-wrap:wrap">
                      <n-tag v-for="s in preview.matched_skills" :key="s" type="success" size="small">{{ s }}</n-tag>
                    </n-space>
                    <n-text v-else depth="3" style="font-size:12px">— none —</n-text>
                  </div>
                  <div v-if="preview.missing_skills.length" style="margin-top:8px">
                    <n-text style="font-size:11px;color:#d03050;font-weight:600;text-transform:uppercase;letter-spacing:0.4px;display:block;margin-bottom:4px">Gaps</n-text>
                    <n-space size="small" style="flex-wrap:wrap">
                      <n-tag v-for="s in preview.missing_skills" :key="s" type="error" size="small">{{ s }}</n-tag>
                    </n-space>
                  </div>
                </n-card>

                <!-- Qualifications Coverage (LLM-based) -->
                <n-card size="small" style="margin-bottom:10px;background:#1a1a1a" v-if="qualificationDetails.length > 0">
                  <template #header>
                    <div style="display:flex;align-items:center;justify-content:space-between">
                      <n-tooltip trigger="hover">
                        <template #trigger>
                          <n-text style="font-size:12px;color:#aaa;text-transform:uppercase;letter-spacing:0.4px;cursor:help">Qualifications</n-text>
                        </template>
                        LLM evaluation of each non-negotiable requirement: experience years, role type, certifications.
                      </n-tooltip>
                      <n-text :style="`font-size:12px;font-weight:700;color:${reqPct >= 80 ? '#18a058' : reqPct >= 60 ? '#f0a020' : '#d03050'}`">
                        {{ qualificationDetails.filter(r => r.matched).length }}/{{ qualificationDetails.length }}
                      </n-text>
                    </div>
                  </template>
                  <n-space vertical size="small">
                    <div
                      v-for="req in qualificationDetails" :key="req.item"
                      style="display:flex;align-items:flex-start;gap:6px"
                    >
                      <n-icon :color="req.matched ? '#18a058' : '#d03050'" size="14" style="flex-shrink:0;margin-top:2px">
                        <svg v-if="req.matched" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
                        <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                      </n-icon>
                      <div>
                        <n-text :style="`font-size:12px;color:${req.matched ? '#e0e0e0' : '#aaa'}`">{{ req.item }}</n-text>
                        <n-text depth="3" style="font-size:11px;display:block;margin-top:1px">{{ req.reason }}</n-text>
                      </div>
                    </div>
                  </n-space>
                </n-card>

                <!-- Keyword Coverage -->
                <n-card size="small" style="background:#1a1a1a" v-if="activeKwDetail">
                  <template #header>
                    <div style="display:flex;align-items:center;justify-content:space-between">
                      <n-tooltip trigger="hover">
                        <template #trigger>
                          <n-text style="font-size:12px;color:#aaa;text-transform:uppercase;letter-spacing:0.4px;cursor:help">ATS Coverage</n-text>
                        </template>
                        Literal keyword scan simulating ATS systems. Shows which exact strings appear in your resume text. Low score = missing explicit keywords, not missing skills. Required 1.0x, Preferred 0.6x, Nice-to-have 0.2x.
                      </n-tooltip>
                      <n-text :style="`font-size:12px;font-weight:700;color:${kwPct >= 70 ? '#18a058' : kwPct >= 50 ? '#f0a020' : '#d03050'}`">
                        {{ kwPct }}%
                      </n-text>
                    </div>
                  </template>
                  <n-space vertical size="small">
                    <!-- Matched (flat across all tiers) -->
                    <template v-if="activeKwDetail.matched_keywords.length > 0">
                      <n-text style="font-size:10px;color:#18a058;text-transform:uppercase;letter-spacing:0.3px">Matched</n-text>
                      <n-space size="small" style="flex-wrap:wrap;margin-bottom:6px">
                        <n-tag v-for="kw in activeKwDetail.matched_keywords" :key="'m-' + kw" type="success" size="small">{{ kw }}</n-tag>
                      </n-space>
                    </template>
                    <!-- Missing per tier -->
                    <template v-if="activeKwDetail.tech_required?.missing?.length > 0">
                      <n-text style="font-size:10px;color:#d03050;text-transform:uppercase;letter-spacing:0.3px">Missing Required</n-text>
                      <n-space size="small" style="flex-wrap:wrap;margin-bottom:6px">
                        <n-tag v-for="kw in activeKwDetail.tech_required.missing" :key="'req-x-' + kw" type="error" size="small">{{ kw }}</n-tag>
                      </n-space>
                    </template>
                    <template v-if="activeKwDetail.tech_preferred?.missing?.length > 0">
                      <n-text style="font-size:10px;color:#f0a020;text-transform:uppercase;letter-spacing:0.3px">Missing Preferred</n-text>
                      <n-space size="small" style="flex-wrap:wrap;margin-bottom:6px">
                        <n-tag v-for="kw in activeKwDetail.tech_preferred.missing" :key="'pref-x-' + kw" type="warning" size="small">{{ kw }}</n-tag>
                      </n-space>
                    </template>
                    <template v-if="activeKwDetail.nice_to_have?.missing?.length > 0">
                      <n-text style="font-size:10px;color:#888;text-transform:uppercase;letter-spacing:0.3px">Missing Nice-to-have</n-text>
                      <n-space size="small" style="flex-wrap:wrap;margin-bottom:4px">
                        <n-tag v-for="kw in activeKwDetail.nice_to_have.missing" :key="'n2h-x-' + kw" size="small">{{ kw }}</n-tag>
                      </n-space>
                    </template>
                    <n-text v-if="!activeKwDetail.tech_required || activeKwDetail.tech_required.total === 0" depth="3" style="font-size:12px">— no keywords extracted —</n-text>
                  </n-space>
                </n-card>

                <!-- Skill Gap Suggestions -->
                <n-card v-if="gapSuggestions.length > 0" size="small" style="background:#1a1a1a;margin-bottom:10px">
                  <template #header>
                    <n-tooltip trigger="hover">
                      <template #trigger>
                        <n-text style="font-size:12px;color:#aaa;text-transform:uppercase;letter-spacing:0.4px;cursor:help">Gap Suggestions</n-text>
                      </template>
                      JD keywords missing from your selected items, but present in your other experiences or projects. Consider swapping items to cover these gaps.
                    </n-tooltip>
                  </template>
                  <n-space vertical size="small">
                    <div v-for="gap in gapSuggestions" :key="gap.missing_keyword" style="display:flex;flex-direction:column;gap:2px">
                      <div style="display:flex;align-items:center;gap:6px">
                        <n-tag type="warning" size="small">{{ gap.missing_keyword }}</n-tag>
                        <n-text depth="3" style="font-size:11px">missing from selected</n-text>
                      </div>
                      <n-text depth="3" style="font-size:11px;padding-left:4px;color:#888">
                        Found in: {{ gap.covered_by.join(', ') }}
                      </n-text>
                    </div>
                  </n-space>
                </n-card>

                <!-- Experience Selection -->
                <n-card size="small" style="background:#1a1a1a;margin-bottom:10px" v-if="preview && preview.all_experiences.length">
                  <template #header>
                    <div style="display:flex;align-items:center;justify-content:space-between">
                      <n-text style="font-size:12px;color:#aaa;text-transform:uppercase;letter-spacing:0.4px">Experiences</n-text>
                      <n-text depth="3" style="font-size:11px">{{ selectedExpIndices.length }} selected</n-text>
                    </div>
                  </template>
                  <n-space vertical size="small">
                    <div
                      v-for="{ exp, idx } in sortedExpList"
                      :key="idx"
                      style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;border-bottom:1px solid #2a2a2a"
                    >
                      <n-checkbox
                        :checked="selectedExpIndices.includes(idx)"
                        @update:checked="(v: boolean) => { if (v) selectedExpIndices.push(idx); else selectedExpIndices.splice(selectedExpIndices.indexOf(idx), 1) }"
                        style="flex-shrink:0;margin-top:2px"
                      />
                      <div style="flex:1;min-width:0">
                        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                          <n-text style="font-size:12px;font-weight:600">{{ exp.title }}</n-text>
                          <n-text depth="3" style="font-size:11px">@ {{ exp.company }}</n-text>
                          <n-tag v-if="preview.topn_experience_indices.includes(idx)" size="tiny" type="info">AI pick</n-tag>
                        </div>
                        <n-text depth="3" style="font-size:11px">{{ exp.start_date }} – {{ exp.end_date ?? 'present' }}</n-text>
                      </div>
                    </div>
                  </n-space>
                </n-card>

                <!-- Project Selection -->
                <n-card size="small" style="background:#1a1a1a;margin-bottom:12px" v-if="preview && preview.all_projects.length">
                  <template #header>
                    <div style="display:flex;align-items:center;justify-content:space-between">
                      <n-text style="font-size:12px;color:#aaa;text-transform:uppercase;letter-spacing:0.4px">Projects</n-text>
                      <n-text depth="3" style="font-size:11px">{{ selectedProjIndices.length }} selected</n-text>
                    </div>
                  </template>
                  <n-space vertical size="small">
                    <div
                      v-for="{ proj, idx } in sortedProjList"
                      :key="idx"
                      style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;border-bottom:1px solid #2a2a2a"
                    >
                      <n-checkbox
                        :checked="selectedProjIndices.includes(idx)"
                        @update:checked="(v: boolean) => { if (v) selectedProjIndices.push(idx); else selectedProjIndices.splice(selectedProjIndices.indexOf(idx), 1) }"
                        style="flex-shrink:0;margin-top:2px"
                      />
                      <div style="flex:1;min-width:0">
                        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                          <n-text style="font-size:12px;font-weight:600">{{ proj.name }}</n-text>
                          <n-tag v-if="preview.topn_project_indices.includes(idx)" size="tiny" type="info">AI pick</n-tag>
                        </div>
                        <n-text depth="3" style="font-size:11px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;display:block;max-width:200px">{{ proj.description }}</n-text>
                      </div>
                    </div>
                  </n-space>
                </n-card>

                <!-- Regenerate button (shown after first auto-generate) -->
                <n-button
                  type="primary"
                  block
                  :loading="draftLoading"
                  :disabled="selectedExpIndices.length === 0 && selectedProjIndices.length === 0"
                  @click="runGenerate"
                  style="margin-top:4px"
                >
                  {{ draftLoading ? 'Generating...' : 'Regenerate with Selection' }}
                </n-button>
                <n-alert v-if="generateError" type="error" style="margin-top:8px;font-size:12px">{{ generateError }}</n-alert>
              </div>
            </n-tab-pane>

            <!-- Content tab -->
            <n-tab-pane name="content" tab="Content" :disabled="draftLoading || !draft" style="flex: 1; overflow-y: auto; padding: 0">
              <div v-if="draft" style="padding: 8px 0">

                <!-- Section visibility -->
                <n-card size="small" title="Sections" style="margin-bottom: 10px">
                  <n-space vertical size="small">
                    <div v-for="sec in sectionToggles" :key="sec.key" style="display:flex;align-items:center;justify-content:space-between">
                      <n-text style="font-size:13px">{{ sec.label }}</n-text>
                      <n-switch v-model:value="draft[sec.key]" size="small" />
                    </div>
                  </n-space>
                  <n-divider style="margin: 10px 0" />
                  <n-text depth="3" style="font-size:12px;display:block;margin-bottom:8px">Custom Sections</n-text>
                  <n-space vertical size="small">
                    <n-card
                      v-for="(cs, ci) in draft.custom_sections"
                      :key="ci"
                      size="small"
                      :style="{ background: '#1a1a1a' }"
                    >
                      <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
                        <n-input v-model:value="cs.title" size="small" placeholder="Section title" style="flex:1" />
                        <n-button size="tiny" type="error" quaternary @click="draft.custom_sections.splice(ci, 1)">Remove</n-button>
                      </div>
                      <n-space vertical size="small">
                        <div v-for="(_, bi) in cs.bullets" :key="bi" style="display:flex;gap:6px;align-items:flex-start">
                          <n-input v-model:value="cs.bullets[bi]" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" style="flex:1" />
                          <n-button size="tiny" quaternary type="error" style="margin-top:4px;flex-shrink:0" @click="cs.bullets.splice(bi,1)">Del</n-button>
                        </div>
                        <n-button size="tiny" dashed @click="cs.bullets.push('')">+ Add bullet</n-button>
                      </n-space>
                    </n-card>
                  </n-space>
                  <n-button size="small" dashed style="margin-top:8px;width:100%" @click="addCustomSection">+ Add Custom Section</n-button>
                </n-card>

                <!-- Contact Info -->
                <n-card size="small" title="Contact Info" style="margin-bottom: 10px">
                  <n-grid :cols="2" :x-gap="10" :y-gap="4">
                    <n-gi><n-form-item label="Email" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="draft.contact_info!.email" placeholder="you@example.com" size="small" />
                    </n-form-item></n-gi>
                    <n-gi><n-form-item label="Phone" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="draft.contact_info!.phone" placeholder="+1 555 000 0000" size="small" />
                    </n-form-item></n-gi>
                    <n-gi :span="2"><n-form-item label="Location" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="draft.contact_info!.location" placeholder="City, Province / State, Country" size="small" />
                    </n-form-item></n-gi>
                    <n-gi><n-form-item label="LinkedIn" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="draft.contact_info!.linkedin" placeholder="linkedin.com/in/yourname" size="small" />
                    </n-form-item></n-gi>
                    <n-gi><n-form-item label="GitHub" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="draft.contact_info!.github" placeholder="github.com/yourname" size="small" />
                    </n-form-item></n-gi>
                    <n-gi :span="2"><n-form-item label="Website" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="draft.contact_info!.website" placeholder="https://yoursite.com" size="small" />
                    </n-form-item></n-gi>
                  </n-grid>
                </n-card>

                <!-- Summary -->
                <n-card size="small" style="margin-bottom: 10px" data-section="summary">
                  <template #header>
                    <n-space align="center" justify="space-between">
                      <span style="font-size: 13px">Summary</span>
                      <n-button size="tiny" quaternary @click="openComment('summary', 'Summary')">Comment</n-button>
                    </n-space>
                  </template>
                  <n-input v-model:value="draft.summary" type="textarea" :rows="3" placeholder="Professional summary..." size="small" />
                </n-card>

                <!-- Experiences -->
                <n-card size="small" title="Work Experience" style="margin-bottom: 10px" ref="expCardRef">
                  <n-collapse v-model:expanded-names="expandedExp">
                    <n-collapse-item v-for="(exp, ei) in draft.experiences" :key="ei" :name="String(ei)">
                      <template #header>
                        <n-space align="center" size="small" style="width:100%;justify-content:space-between">
                          <n-text style="font-size:12px;font-weight:500">{{ exp.title }} @ {{ exp.company }}</n-text>
                          <n-button size="tiny" quaternary @click.stop="openComment(`experiences[${ei}]`, `${exp.title} @ ${exp.company}`)">Comment</n-button>
                        </n-space>
                      </template>
                      <n-grid :cols="3" :x-gap="8" style="margin-bottom:10px">
                        <n-gi><n-form-item label="Title" label-placement="top" :show-feedback="false"><n-input v-model:value="exp.title" size="small" /></n-form-item></n-gi>
                        <n-gi><n-form-item label="Company" label-placement="top" :show-feedback="false"><n-input v-model:value="exp.company" size="small" /></n-form-item></n-gi>
                        <n-gi><n-form-item label="Location" label-placement="top" :show-feedback="false"><n-input v-model:value="exp.location" size="small" /></n-form-item></n-gi>
                        <n-gi><n-form-item label="Start" label-placement="top" :show-feedback="false"><n-input v-model:value="exp.start_date" size="small" /></n-form-item></n-gi>
                        <n-gi><n-form-item label="End" label-placement="top" :show-feedback="false"><n-input v-model:value="exp.end_date" size="small" placeholder="present" /></n-form-item></n-gi>
                      </n-grid>
                      <n-space vertical size="small">
                        <div v-for="(bullet, bi) in exp.bullets" :key="bi" style="display:flex;gap:6px;align-items:flex-start">
                          <n-input v-model:value="bullet.text" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" style="flex:1" />
                          <n-button size="tiny" quaternary type="error" style="margin-top:4px;flex-shrink:0" @click="exp.bullets.splice(bi,1)">Del</n-button>
                        </div>
                        <n-button size="tiny" dashed @click="exp.bullets.push({text:'',highlighted:false})">+ Add bullet</n-button>
                      </n-space>
                    </n-collapse-item>
                  </n-collapse>
                </n-card>

                <!-- Education -->
                <n-card size="small" title="Education" style="margin-bottom: 10px">
                  <n-space vertical size="small">
                    <n-card v-for="(edu, i) in draft.education" :key="i" size="small">
                      <n-grid :cols="3" :x-gap="8">
                        <n-gi><n-form-item label="Institution" label-placement="top" :show-feedback="false"><n-input v-model:value="edu.institution" size="small" /></n-form-item></n-gi>
                        <n-gi><n-form-item label="Degree" label-placement="top" :show-feedback="false"><n-input v-model:value="edu.degree" size="small" /></n-form-item></n-gi>
                        <n-gi><n-form-item label="Field" label-placement="top" :show-feedback="false"><n-input v-model:value="edu.field_of_study" size="small" /></n-form-item></n-gi>
                        <n-gi><n-form-item label="Start" label-placement="top" :show-feedback="false"><n-input v-model:value="edu.start_date" size="small" /></n-form-item></n-gi>
                        <n-gi><n-form-item label="End" label-placement="top" :show-feedback="false"><n-input v-model:value="edu.end_date" size="small" placeholder="present" /></n-form-item></n-gi>
                        <n-gi><n-form-item label="GPA" label-placement="top" :show-feedback="false"><n-input v-model:value="edu.gpa" size="small" placeholder="optional" /></n-form-item></n-gi>
                      </n-grid>
                    </n-card>
                  </n-space>
                </n-card>

                <!-- Projects -->
                <n-card size="small" title="Projects" style="margin-bottom: 10px" ref="projCardRef">
                  <n-collapse v-model:expanded-names="expandedProj">
                    <n-collapse-item v-for="(proj, pi) in draft.projects" :key="pi" :name="String(pi)">
                      <template #header>
                        <n-space align="center" size="small" style="width:100%;justify-content:space-between">
                          <n-text style="font-size:12px;font-weight:500">{{ proj.name }}</n-text>
                          <n-button size="tiny" quaternary @click.stop="openComment(`projects[${pi}]`, proj.name)">Comment</n-button>
                        </n-space>
                      </template>
                      <n-grid :cols="2" :x-gap="8" style="margin-bottom:8px">
                        <n-gi><n-form-item label="Name" label-placement="top" :show-feedback="false"><n-input v-model:value="proj.name" size="small" /></n-form-item></n-gi>
                        <n-gi><n-form-item label="URL" label-placement="top" :show-feedback="false"><n-input v-model:value="proj.url" size="small" placeholder="optional" /></n-form-item></n-gi>
                        <n-gi :span="2"><n-form-item label="Description" label-placement="top" :show-feedback="false"><n-input v-model:value="proj.description" type="textarea" :rows="2" size="small" /></n-form-item></n-gi>
                      </n-grid>
                      <n-space vertical size="small">
                        <div v-for="(bullet, bi) in proj.bullets" :key="bi" style="display:flex;gap:6px;align-items:flex-start">
                          <n-input v-model:value="bullet.text" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" style="flex:1" />
                          <n-button size="tiny" quaternary type="error" style="margin-top:4px;flex-shrink:0" @click="proj.bullets.splice(bi,1)">Del</n-button>
                        </div>
                        <n-button size="tiny" dashed @click="proj.bullets.push({text:'',highlighted:false})">+ Add bullet</n-button>
                      </n-space>
                    </n-collapse-item>
                  </n-collapse>
                </n-card>

                <!-- Skills -->
                <n-card size="small" title="Skills" style="margin-bottom: 10px">
                  <n-space wrap size="small">
                    <n-tag v-for="(skill, si) in draft.skills" :key="si" :type="proficiencyType(skill.proficiency)" size="small">
                      {{ skill.category }}: {{ skill.name }}
                    </n-tag>
                  </n-space>
                </n-card>

              </div>
            </n-tab-pane>

            <!-- Layout tab -->
            <n-tab-pane name="layout" tab="Layout" style="flex:1;overflow-y:auto;padding:0">
              <LayoutPanel :settings="layoutSettings" @update:settings="layoutSettings = $event" />
            </n-tab-pane>

            <!-- Copilot tab -->
            <n-tab-pane name="copilot" style="flex:1;overflow-y:auto;padding:0">
              <template #tab>
                <n-space align="center" size="small" :wrap="false">
                  <span>AI Copilot</span>
                  <n-badge
                    v-if="diagnosticReport"
                    :value="diagnosticReport.tasks.filter(t => !verifiedTaskIds.has(t.id)).length"
                    :max="99"
                    type="error"
                  />
                </n-space>
              </template>

              <!-- Loading state -->
              <div v-if="diagnoseLoading" style="display:flex;align-items:center;justify-content:center;padding:32px;gap:12px">
                <n-spin size="small" />
                <n-text depth="3" style="font-size:13px">Analyzing resume...</n-text>
              </div>

              <!-- Empty state -->
              <div v-else-if="!diagnosticReport" style="padding:32px;text-align:center">
                <n-text depth="3" style="font-size:13px;display:block;margin-bottom:16px">No diagnosis results yet.</n-text>
                <n-button type="primary" size="small" :disabled="!sessionJd" @click="runDiagnose">Run Diagnosis</n-button>
              </div>

              <div v-else style="padding:12px 8px">
                <!-- Score summary -->
                <n-card size="small" style="margin-bottom:12px;background:#1a1a1a">
                  <n-space vertical size="small">
                    <div style="display:flex;align-items:center;gap:8px">
                      <n-tooltip trigger="hover">
                        <template #trigger>
                          <n-text style="font-size:12px;min-width:72px;color:#aaa;cursor:help">Tech Keywords</n-text>
                        </template>
                        Literal coverage of required tech keywords (tools, languages, frameworks). See Match tab for breakdown.
                      </n-tooltip>
                      <n-progress
                        type="line"
                        :percentage="Math.round(diagnosticReport.req_score * 100)"
                        :color="diagnosticReport.req_score >= 0.8 ? '#18a058' : diagnosticReport.req_score >= 0.6 ? '#f0a020' : '#d03050'"
                        :rail-color="'#2a2a2a'"
                        style="flex:1"
                      />
                      <n-text style="font-size:12px;font-weight:600;min-width:36px">
                        {{ Math.round(diagnosticReport.req_score * 100) }}%
                      </n-text>
                    </div>
                    <div style="display:flex;align-items:center;gap:8px">
                      <n-tooltip trigger="hover">
                        <template #trigger>
                          <n-text style="font-size:12px;min-width:72px;color:#aaa;cursor:help">Weighted Score</n-text>
                        </template>
                        Weighted keyword composite: tech keywords (0.8×) + preferred qualifications (0.5×). See Match tab for breakdown.
                      </n-tooltip>
                      <n-progress
                        type="line"
                        :percentage="Math.round(diagnosticReport.kw_score * 100)"
                        :color="diagnosticReport.kw_score >= 0.7 ? '#18a058' : diagnosticReport.kw_score >= 0.5 ? '#f0a020' : '#d03050'"
                        :rail-color="'#2a2a2a'"
                        style="flex:1"
                      />
                      <n-text style="font-size:12px;font-weight:600;min-width:36px">
                        {{ Math.round(diagnosticReport.kw_score * 100) }}%
                      </n-text>
                    </div>
                  </n-space>
                  <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:8px">
                    <n-tooltip trigger="hover" placement="top">
                      <template #trigger>
                        <n-button
                          v-show="modifiedSections.size > 0"
                          size="tiny"
                          type="primary"
                          ghost
                          :loading="batchVerifying"
                          :disabled="!canBatchVerify"
                          @click="runBatchVerify"
                        >
                          Verify Changes ({{ modifiedSections.size }})
                        </n-button>
                      </template>
                      Check whether your recent edits resolved any pending issues
                    </n-tooltip>
                    <n-button size="tiny" quaternary :loading="diagnoseLoading" @click="runDiagnose">
                      Re-diagnose
                    </n-button>
                  </div>
                </n-card>

                <!-- Task list -->
                <n-collapse :default-expanded-names="['tier1']">
                  <!-- Tier 1: Critical -->
                  <n-collapse-item
                    v-if="diagnosticReport.tasks.some(t => t.tier === 'tier1')"
                    name="tier1"
                  >
                    <template #header>
                      <n-space align="center" size="small">
                        <n-text style="font-size:12px;font-weight:600">Critical</n-text>
                        <n-badge
                          :value="diagnosticReport.tasks.filter(t => t.tier === 'tier1' && !verifiedTaskIds.has(t.id)).length"
                          type="error"
                        />
                      </n-space>
                    </template>
                    <div
                      v-for="task in diagnosticReport.tasks.filter(t => t.tier === 'tier1')"
                      :key="task.id"
                      class="task-card"
                      :class="{ 'task-done': verifiedTaskIds.has(task.id) }"
                      @mouseenter="onTaskHover(task)"
                      @mouseleave="onTaskLeave()"
                    >
                      <n-space align="center" justify="space-between" :wrap="false">
                        <n-text style="font-size:12px;font-weight:500">{{ task.title }}</n-text>
                        <n-tag type="error" size="tiny">Critical</n-tag>
                      </n-space>
                      <n-text depth="3" style="font-size:11px;display:block;margin-top:4px;line-height:1.5">
                        {{ task.description }}
                      </n-text>
                      <n-button
                        v-if="task.action_label && task.section"
                        size="tiny"
                        type="primary"
                        ghost
                        style="margin-top:6px"
                        @click="goToSection(task.section)"
                      >
                        {{ task.action_label }}
                      </n-button>
                    </div>
                  </n-collapse-item>

                  <!-- Tier 2: Suggestions -->
                  <n-collapse-item
                    v-if="diagnosticReport.tasks.some(t => t.tier === 'tier2')"
                    name="tier2"
                  >
                    <template #header>
                      <n-space align="center" size="small">
                        <n-text style="font-size:12px;font-weight:600">Suggestions</n-text>
                        <n-badge
                          :value="diagnosticReport.tasks.filter(t => t.tier === 'tier2' && !verifiedTaskIds.has(t.id)).length"
                          type="warning"
                        />
                      </n-space>
                    </template>
                    <div
                      v-for="task in diagnosticReport.tasks.filter(t => t.tier === 'tier2')"
                      :key="task.id"
                      class="task-card"
                      :class="{ 'task-done': verifiedTaskIds.has(task.id) }"
                      @mouseenter="onTaskHover(task)"
                      @mouseleave="onTaskLeave()"
                    >
                      <n-space align="center" justify="space-between" :wrap="false">
                        <n-text style="font-size:12px;font-weight:500">{{ task.title }}</n-text>
                        <n-tag type="warning" size="tiny">Suggestion</n-tag>
                      </n-space>
                      <n-text depth="3" style="font-size:11px;display:block;margin-top:4px;line-height:1.5">
                        {{ task.description }}
                      </n-text>
                      <n-space size="small" style="margin-top:6px">
                        <n-button
                          v-if="task.action_label && task.section"
                          size="tiny"
                          ghost
                          @click="goToSection(task.section)"
                        >
                          {{ task.action_label }}
                        </n-button>
                        <n-button
                          v-if="task.verify_condition"
                          size="tiny"
                          :loading="verifyingTaskId === task.id"
                          :type="verifiedTaskIds.has(task.id) ? 'success' : 'default'"
                          @click="verifyTask(task)"
                        >
                          {{ verifiedTaskIds.has(task.id) ? 'Verified' : 'Verify' }}
                        </n-button>
                      </n-space>
                    </div>
                  </n-collapse-item>

                  <!-- Tier 3: Polish -->
                  <n-collapse-item
                    v-if="diagnosticReport.tasks.some(t => t.tier === 'tier3')"
                    name="tier3"
                  >
                    <template #header>
                      <n-space align="center" size="small">
                        <n-text style="font-size:12px;font-weight:600">Polish</n-text>
                        <n-badge
                          :value="diagnosticReport.tasks.filter(t => t.tier === 'tier3' && !verifiedTaskIds.has(t.id)).length"
                          type="success"
                        />
                      </n-space>
                    </template>
                    <div
                      v-for="task in diagnosticReport.tasks.filter(t => t.tier === 'tier3')"
                      :key="task.id"
                      class="task-card"
                      :class="{ 'task-done': verifiedTaskIds.has(task.id) }"
                      @mouseenter="onTaskHover(task)"
                      @mouseleave="onTaskLeave()"
                    >
                      <n-space align="center" justify="space-between" :wrap="false">
                        <n-text style="font-size:12px;font-weight:500">{{ task.title }}</n-text>
                        <n-tag type="success" size="tiny">Polish</n-tag>
                      </n-space>
                      <n-text depth="3" style="font-size:11px;display:block;margin-top:4px;line-height:1.5">
                        {{ task.description }}
                      </n-text>
                      <div v-if="task.original_text" style="margin-top:6px">
                        <n-text style="font-size:10px;color:#666;display:block;margin-bottom:2px">Original:</n-text>
                        <n-text
                          style="font-size:10px;color:#888;display:block;background:#1a1a1a;padding:4px 6px;border-radius:3px;margin-bottom:6px;font-family:monospace;white-space:pre-wrap"
                        >"{{ task.original_text }}"</n-text>
                        <n-button
                          size="tiny"
                          type="primary"
                          ghost
                          @click="discussInChat(task)"
                        >
                          Discuss in Chat
                        </n-button>
                      </div>
                      <div v-else style="margin-top:6px">
                        <n-button size="tiny" ghost @click="discussInChat(task)">Discuss in Chat</n-button>
                      </div>
                    </div>
                  </n-collapse-item>
                </n-collapse>
              </div>
            </n-tab-pane>
          </n-tabs>

          <!-- Chat -->
          <ChatPanel
            v-if="currentSessionId && draft"
            ref="chatPanelRef"
            :session-id="currentSessionId"
            :draft="draft"
            :pending-scope-init="pendingScope ?? undefined"
            @patch="handlePatch"
          />
        </div>

        <!-- Right pane: live preview -->
        <div class="stage3-right">
          <div v-if="draftLoading" class="draft-loading-pane">
            <n-spin size="large" />
            <n-text depth="3" style="font-size:13px;margin-top:16px">Tailoring your resume...</n-text>
          </div>
          <div v-else-if="generateError" class="draft-loading-pane">
            <n-alert type="error" style="max-width:360px">{{ generateError }}</n-alert>
          </div>
          <ResumePreview v-else-if="draft" ref="previewRef" :draft="draft" :settings="layoutSettings" :full-name="userName" @section-click="onPreviewSectionClick" />
        </div>
      </div>
    </template>
  </div>

  <button
    v-if="selectionBtn"
    ref="quoteButtonRef"
    class="selection-quote-btn"
    :style="{ left: selectionBtn.x + 'px', top: (selectionBtn.y - 38) + 'px' }"
    @click="quoteSelection"
  >
    Quote in chat
  </button>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { analyzeJD, batchVerify, confirmGenerate, defaultLayoutSettings, diagnose, getProfile, getSession, microValidate, updateSessionDraft } from '../api/client'
import type {
  BatchVerifyResponse,
  CategoryMatchResult,
  ChatScope,
  DiagnosticReport,
  DiagnosticTask,
  JobDescription,
  KeywordMatchResult,
  LayoutSettings,
  MasterProfile,
  MatchingPreview,
  PipelineConfig,
  ResumePatch,
  SkillGapSuggestion,
  TailoredResumeDraft,
  WorkExperience,
  Project,
} from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useRoute } from 'vue-router'
import ChatPanel from '../components/ChatPanel.vue'
import ResumePreview from '../components/ResumePreview.vue'
import LayoutPanel from '../components/LayoutPanel.vue'

const auth = useAuthStore()
const route = useRoute()
const message = useMessage()
const token = () => auth.token!

const currentSessionId = ref<string | null>(null)
const userName = ref('')
const layoutSettings = ref<LayoutSettings>(defaultLayoutSettings())

// selected experience/project indices for generation (user-editable)
const selectedExpIndices = ref<number[]>([])
const selectedProjIndices = ref<number[]>([])

type Stage = 'jd' | 'result'
const stage = ref<Stage>('jd')

// ── stage 1 ────────────────────────────────────────────────────
const jdText = ref(`We are looking for a Senior Backend Engineer to join our platform team.

Requirements:
- 4+ years of experience in Python backend development
- Strong experience with FastAPI or Django REST Framework
- Proficiency in PostgreSQL and Redis
- Experience with Docker and Kubernetes
- Familiarity with LLM tooling (LangChain, OpenAI API) is a strong plus

Soft skills: strong communication, collaborative mindset, proactive problem-solving.`)

const analyzeLoading = ref(false)
const analyzeError = ref('')
const draftLoading = ref(false)
const generateError = ref('')

// Stored for session_id reference after analyze
const preview = ref<MatchingPreview | null>(null)
const matchPct = computed(() => preview.value ? Math.round(preview.value.match_score * 100) : 0)

const config: PipelineConfig = {
  initial_threshold: 0.8,
  decay_per_retry: 0.05,
  min_threshold: 0.6,
  max_retries: 3,
}

// kwDetail: from session_detail (draft-based) or preview (profile-based, analyze phase)
const kwDetail = ref<KeywordMatchResult | null>(null)

// qualificationDetails: LLM-based per-item judgment from SkillMatcher
const qualificationDetails = computed(() => preview.value?.qualification_details ?? [])

// gapSuggestions: JD keywords missing from selected items but found in unselected ones
const gapSuggestions = computed<SkillGapSuggestion[]>(() => preview.value?.skill_gap_suggestions ?? [])

const reqPct = computed(() => {
  const qd = qualificationDetails.value
  if (qd.length > 0) {
    return Math.round(qd.filter(r => r.matched).length / qd.length * 100)
  }
  return 0
})
const kwPct = computed(() => kwDetail.value ? Math.round(kwDetail.value.score * 100) : 0)

// activeKwDetail: prefer session-level detail (draft-based); fall back to preview (profile-based)
const activeKwDetail = computed<KeywordMatchResult | null>(
  () => kwDetail.value ?? preview.value?.kw_detail ?? null
)


// Sorted experience/project lists: selected first, then unselected
const sortedExpList = computed<Array<{ exp: WorkExperience; idx: number }>>(() => {
  if (!preview.value) return []
  const selected = preview.value.all_experiences
    .map((exp, i) => ({ exp, idx: i }))
    .filter(e => selectedExpIndices.value.includes(e.idx))
  const rest = preview.value.all_experiences
    .map((exp, i) => ({ exp, idx: i }))
    .filter(e => !selectedExpIndices.value.includes(e.idx))
  return [...selected, ...rest]
})

const sortedProjList = computed<Array<{ proj: Project; idx: number }>>(() => {
  if (!preview.value) return []
  const selected = preview.value.all_projects
    .map((proj, j) => ({ proj, idx: j }))
    .filter(p => selectedProjIndices.value.includes(p.idx))
  const rest = preview.value.all_projects
    .map((proj, j) => ({ proj, idx: j }))
    .filter(p => !selectedProjIndices.value.includes(p.idx))
  return [...selected, ...rest]
})

async function runAnalyze(): Promise<void> {
  analyzeError.value = ''
  generateError.value = ''
  analyzeLoading.value = true
  try {
    const data = await analyzeJD(token(), jdText.value)
    currentSessionId.value = data.session_id
    preview.value = data
    selectedExpIndices.value = [...(data.topn_experience_indices ?? [])]
    selectedProjIndices.value = [...(data.topn_project_indices ?? [])]
    stage.value = 'result'
    leftActiveTab.value = 'match'
    analyzeLoading.value = false

    // auto-generate with AI pick
    await runGenerate()
  } catch (e) {
    analyzeError.value = (e as Error).message
    analyzeLoading.value = false
  }
}

async function runGenerate(): Promise<void> {
  if (!currentSessionId.value) return
  generateError.value = ''
  draftLoading.value = true
  try {
    const draftData = await confirmGenerate(
      token(),
      currentSessionId.value,
      { ...config },
      undefined,
      undefined,
      selectedExpIndices.value,
      selectedProjIndices.value,
    )
    draft.value = {
      show_summary: true,
      show_experiences: true,
      show_education: true,
      show_projects: true,
      show_skills: true,
      custom_sections: [],
      ...draftData,
      contact_info: draftData.contact_info ?? {},
    }
    leftActiveTab.value = 'content'
    try {
      const detail = await getSession(token(), currentSessionId.value)
      if (detail.kw_detail) kwDetail.value = detail.kw_detail
      if (detail.jd) sessionJd.value = detail.jd
    } catch { /* non-critical */ }
    runDiagnose()
  } catch (e) {
    generateError.value = (e as Error).message
  } finally {
    draftLoading.value = false
  }
}

onMounted(async () => {
  document.addEventListener('mousedown', onDocMouseDown)

  try {
    const profile = await getProfile(token())
    userName.value = profile.full_name
    profileRef.value = profile
  } catch { /* non-critical */ }

  const sid = route.query.session_id as string | undefined
  if (sid) {
    await loadSessionById(sid)
  }
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onDocMouseDown)
})

async function loadSessionById(sid: string): Promise<void> {
  try {
    const detail = await getSession(token(), sid)
    currentSessionId.value = sid
    if (detail.status === 'draft_ready' && detail.tailored_draft) {
      draft.value = {
        show_summary: true,
        show_experiences: true,
        show_education: true,
        show_projects: true,
        show_skills: true,
        custom_sections: [],
        ...detail.tailored_draft,
        contact_info: detail.tailored_draft.contact_info ?? {},
      }
      const topnExp = detail.highlighted_experience_indices ?? []
      const topnProj = detail.highlighted_project_indices ?? []
      preview.value = {
        session_id: sid,
        match_score: detail.match_score ?? 0,
        job_title: detail.job_title ?? '',
        company: detail.company,
        matched_skills: detail.matched_skills ?? [],
        missing_skills: detail.missing_skills ?? [],
        highlighted_experience_indices: topnExp,
        highlighted_project_indices: topnProj,
        topn_experience_indices: topnExp,
        topn_project_indices: topnProj,
        all_experiences: detail.all_experiences ?? [],
        all_projects: detail.all_projects ?? [],
        relevance_notes: detail.relevance_notes ?? '',
        qualification_details: detail.qualification_details ?? [],
        kw_detail: detail.kw_detail,
      }
      selectedExpIndices.value = [...topnExp]
      selectedProjIndices.value = [...topnProj]
      if (detail.kw_detail) kwDetail.value = detail.kw_detail
      if (detail.jd) sessionJd.value = detail.jd
      stage.value = 'result'
      const cached = _loadDiagCache(sid)
      if (cached) diagnosticReport.value = cached
    } else {
      // For analyzed/generating sessions, pre-fill the JD and let user re-generate
      jdText.value = detail.jd_text
    }
  } catch {
    // silently ignore — start fresh
  }
}

// ── toolbar score helpers ───────────────────────────────────────
function scoreChipClass(pct: number): string {
  if (pct >= 70) return 'sc-good'
  if (pct >= 50) return 'sc-warn'
  return 'sc-poor'
}

function scoreStatusText(pct: number): string {
  if (pct >= 70) return 'Good'
  if (pct >= 50) return 'Fair'
  return 'Low'
}


const criticalCount = computed(() => {
  if (!diagnosticReport.value) return 0
  return diagnosticReport.value.tasks.filter(t => t.tier === 'tier1' && !verifiedTaskIds.has(t.id)).length
})

const suggestionCount = computed(() => {
  if (!diagnosticReport.value) return 0
  return diagnosticReport.value.tasks.filter(t => t.tier === 'tier2' && !verifiedTaskIds.has(t.id)).length
})

// ── copilot ─────────────────────────────────────────────────────
const profileRef = ref<MasterProfile | null>(null)
const sessionJd = ref<JobDescription | null>(null)
const diagnosticReport = ref<DiagnosticReport | null>(null)
const diagnoseLoading = ref(false)
const leftActiveTab = ref<string>('content')
const verifiedTaskIds = reactive<Set<string>>(new Set())
const verifyingTaskId = ref<string | null>(null)

// ── batch verify: track section-level changes since last diagnose/verify ──
const draftSnapshot = ref<TailoredResumeDraft | null>(null)
const modifiedSections = reactive<Set<string>>(new Set())
const batchVerifying = ref(false)

const pendingSemanticTasks = computed(() =>
  diagnosticReport.value?.tasks.filter(
    t => (t.tier === 'tier2' || t.tier === 'tier3') && !verifiedTaskIds.has(t.id)
  ) ?? []
)

const canBatchVerify = computed(
  () => modifiedSections.size > 0 && pendingSemanticTasks.value.length > 0
)

function buildChangedSections(): Record<string, string> {
  const d = draft.value
  const snap = draftSnapshot.value
  if (!d || !snap) return {}
  // Compute diff directly from current draft vs snapshot at click time,
  // rather than relying on the reactively-maintained modifiedSections set.
  const result: Record<string, string> = {}
  if ((d.summary ?? '') !== (snap.summary ?? '')) {
    result['summary'] = d.summary ?? ''
  }
  d.experiences.forEach((exp, i) => {
    if (JSON.stringify(exp) !== JSON.stringify(snap.experiences[i])) {
      result[`experiences[${i}]`] = exp.bullets
        .map((b: { text: string }) => b.text)
        .filter(Boolean)
        .join('\n')
    }
  })
  d.projects.forEach((proj, i) => {
    if (JSON.stringify(proj) !== JSON.stringify(snap.projects[i])) {
      result[`projects[${i}]`] = proj.bullets
        .map((b: { text: string }) => b.text)
        .filter(Boolean)
        .join('\n')
    }
  })
  return result
}

async function runBatchVerify(): Promise<void> {
  if (!canBatchVerify.value) return
  batchVerifying.value = true
  try {
    const resp: BatchVerifyResponse = await batchVerify(token(), buildChangedSections(), pendingSemanticTasks.value)
    if (resp.resolved.length === 0) {
      message.info('No issues resolved by recent edits')
    } else {
      resp.resolved.forEach(r => {
        verifiedTaskIds.add(r.id)
        message.success(r.reason, { duration: 4000 })
      })
    }
    draftSnapshot.value = JSON.parse(JSON.stringify(draft.value!))
    modifiedSections.clear()
  } catch (e) {
    message.error('Batch verify failed: ' + (e as Error).message)
  } finally {
    batchVerifying.value = false
  }
}

const _DIAG_PREFIX = 'diag_'

function _saveDiagCache(sid: string, report: DiagnosticReport): void {
  try { localStorage.setItem(_DIAG_PREFIX + sid, JSON.stringify(report)) } catch { /* quota */ }
}

function _loadDiagCache(sid: string): DiagnosticReport | null {
  try {
    const raw = localStorage.getItem(_DIAG_PREFIX + sid)
    return raw ? (JSON.parse(raw) as DiagnosticReport) : null
  } catch { return null }
}

async function runDiagnose(): Promise<void> {
  if (!draft.value || !profileRef.value || !sessionJd.value) return
  diagnoseLoading.value = true
  try {
    const report = await diagnose(token(), draft.value, sessionJd.value, profileRef.value)
    diagnosticReport.value = report
    if (currentSessionId.value) _saveDiagCache(currentSessionId.value, report)
  } catch (e) {
    message.error('Diagnosis failed: ' + (e as Error).message)
  } finally {
    diagnoseLoading.value = false
  }
}

function getTaskContext(task: DiagnosticTask): string {
  if (!draft.value) return ''
  const s = task.section
  if (!s || s === 'summary') return draft.value.summary ?? ''
  const m = s.match(/^(experiences|projects)\[(\d+)\]$/)
  if (!m) return draft.value.summary ?? ''
  const idx = parseInt(m[2], 10)
  const items = m[1] === 'experiences' ? draft.value.experiences : draft.value.projects
  const item = items[idx]
  if (!item) return ''
  if (task.bullet_index != null) return item.bullets[task.bullet_index]?.text ?? ''
  return item.bullets.map((b: { text: string }) => b.text).join(' ')
}

async function verifyTask(task: DiagnosticTask): Promise<void> {
  if (!task.verify_condition) return
  verifyingTaskId.value = task.id
  try {
    const result = await microValidate(token(), getTaskContext(task), task.verify_condition)
    if (result.passed) {
      verifiedTaskIds.add(task.id)
      message.success(result.reasoning || 'Condition satisfied')
    } else {
      message.warning(result.reasoning || 'Condition not yet met')
    }
  } catch (e) {
    message.error('Verification failed: ' + (e as Error).message)
  } finally {
    verifyingTaskId.value = null
  }
}

function applyReplacement(task: DiagnosticTask): void {
  if (!draft.value || !task.replaceable || !task.original_text || !task.suggested_text) return
  for (const exp of draft.value.experiences) {
    for (const bullet of exp.bullets) {
      if (bullet.text === task.original_text) {
        bullet.text = task.suggested_text
        verifiedTaskIds.add(task.id)
        message.success('Replacement applied')
        return
      }
    }
  }
  for (const proj of draft.value.projects) {
    for (const bullet of proj.bullets) {
      if (bullet.text === task.original_text) {
        bullet.text = task.suggested_text
        verifiedTaskIds.add(task.id)
        message.success('Replacement applied')
        return
      }
    }
  }
  message.warning('Original text not found in current draft')
}

function goToSection(section: string | null | undefined): void {
  if (!section) return
  leftActiveTab.value = 'content'
  setTimeout(() => {
    const el = document.querySelector(`[data-section="${section}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, 80)
}

// ── stage 3 ────────────────────────────────────────────────────
const draft = ref<TailoredResumeDraft | null>(null)
const saveLoading = ref(false)

watch(diagnosticReport, (report) => {
  if (report && draft.value) {
    draftSnapshot.value = JSON.parse(JSON.stringify(draft.value))
    modifiedSections.clear()
  }
})

watch(draft, (cur) => {
  const snap = draftSnapshot.value
  if (!cur || !snap) return
  if (cur.summary !== snap.summary) modifiedSections.add('summary')
  cur.experiences.forEach((exp, i) => {
    if (JSON.stringify(exp) !== JSON.stringify(snap.experiences[i])) {
      modifiedSections.add(`experiences[${i}]`)
    }
  })
  cur.projects.forEach((proj, i) => {
    if (JSON.stringify(proj) !== JSON.stringify(snap.projects[i])) {
      modifiedSections.add(`projects[${i}]`)
    }
  })
}, { deep: true })
const pendingScope = ref<ChatScope | null>(null)
const chatPanelRef = ref<InstanceType<typeof ChatPanel> | null>(null)
const previewRef = ref<InstanceType<typeof ResumePreview> | null>(null)
const expCardRef = ref<{ $el: HTMLElement } | null>(null)
const projCardRef = ref<{ $el: HTMLElement } | null>(null)
const expandedExp = ref<string[]>([])
const expandedProj = ref<string[]>([])

function onPreviewSectionClick(hlValue: string): void {
  leftActiveTab.value = 'content'
  setTimeout(() => {
    if (hlValue === 'summary') {
      document.querySelector('[data-section="summary"]')
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }
    const m = hlValue.match(/^(exp|proj)-(\d+)/)
    if (!m) return
    const idx = m[2]
    const isExp = m[1] === 'exp'
    if (isExp) {
      expandedExp.value = [idx]
      expCardRef.value?.$el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } else {
      expandedProj.value = [idx]
      projCardRef.value?.$el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, 80)
}

function taskToHlValue(task: DiagnosticTask): string | null {
  const s = task.section
  if (!s) return null
  if (s === 'summary') return 'summary'
  const m = s.match(/^(experiences|projects)\[(\d+)\]$/)
  if (!m) return null
  const prefix = m[1] === 'experiences' ? 'exp' : 'proj'
  const idx = m[2]
  if (task.bullet_index != null) return `${prefix}-${idx}-b-${task.bullet_index}`
  return `${prefix}-${idx}`
}

function onTaskHover(task: DiagnosticTask): void {
  const hlValue = taskToHlValue(task)
  if (hlValue) previewRef.value?.highlightByHl(hlValue)
}

function onTaskLeave(): void {
  previewRef.value?.highlightByHl(null)
}

interface SelectionBtn { x: number; y: number; text: string }
const selectionBtn = ref<SelectionBtn | null>(null)
const quoteButtonRef = ref<HTMLElement | null>(null)

function onLeftMouseUp(e: MouseEvent): void {
  const target = e.target as HTMLElement
  if (!(target instanceof HTMLTextAreaElement)) return
  const start = target.selectionStart ?? 0
  const end = target.selectionEnd ?? 0
  if (start === end) { selectionBtn.value = null; return }
  const text = target.value.substring(start, end).trim()
  if (!text) { selectionBtn.value = null; return }
  selectionBtn.value = { x: e.clientX, y: e.clientY, text }
}

function quoteSelection(): void {
  if (!selectionBtn.value) return
  const label = selectionBtn.value.text.length > 50
    ? selectionBtn.value.text.substring(0, 50) + '...'
    : selectionBtn.value.text
  chatPanelRef.value?.setScope({ path: 'selection', label: `"${label}"` })
  selectionBtn.value = null
}

function onDocMouseDown(e: MouseEvent): void {
  if (quoteButtonRef.value && quoteButtonRef.value.contains(e.target as Node)) return
  selectionBtn.value = null
}

const sectionToggles: { key: keyof TailoredResumeDraft; label: string }[] = [
  { key: 'show_summary', label: 'Summary' },
  { key: 'show_experiences', label: 'Work Experience' },
  { key: 'show_education', label: 'Education' },
  { key: 'show_projects', label: 'Projects' },
  { key: 'show_skills', label: 'Skills' },
]

function addCustomSection(): void {
  if (!draft.value) return
  draft.value.custom_sections.push({ title: '', bullets: [''] })
}

function openComment(path: string, label: string): void {
  pendingScope.value = { path, label }
}

function discussInChat(task: DiagnosticTask): void {
  if (!draft.value) return
  const section = task.section ?? 'summary'
  let label = section
  const m = section.match(/^(experiences|projects)\[(\d+)\]$/)
  if (m) {
    const idx = parseInt(m[2], 10)
    if (m[1] === 'experiences') {
      const exp = draft.value.experiences[idx]
      if (exp) label = `${exp.title} @ ${exp.company}`
    } else {
      const proj = draft.value.projects[idx]
      if (proj) label = proj.name
    }
  } else if (section === 'summary') {
    label = 'Summary'
  }

  // Use bullet-level path when bullet_index is available
  const path =
    task.bullet_index != null && m
      ? `${section}.bullets[${task.bullet_index}]`
      : section

  chatPanelRef.value?.setScope({ path, label })
  const prefillParts = [`Copilot suggestion: ${task.description}`]
  if (task.original_text) prefillParts.push(`\nOriginal bullet: "${task.original_text}"`)
  chatPanelRef.value?.prefill(prefillParts.join(''))
}

function handlePatch(patch: ResumePatch): void {
  if (!draft.value) return
  if (patch.path === 'summary') {
    draft.value.summary = patch.updated_value as string
    return
  }
  const mb = patch.path.match(/^(experiences|projects)\[(\d+)\]\.bullets\[(\d+)\]$/)
  if (mb) {
    const field = mb[1] as 'experiences' | 'projects'
    const itemIdx = parseInt(mb[2])
    const bulletIdx = parseInt(mb[3])
    const item = (draft.value[field] as Array<{ bullets: Array<{ text: string }> }>)[itemIdx]
    if (item?.bullets[bulletIdx] != null) {
      item.bullets[bulletIdx].text = patch.updated_value as string
    }
    return
  }
  const m = patch.path.match(/^(experiences|projects)\[(\d+)\]$/)
  if (m) {
    const field = m[1] as 'experiences' | 'projects'
    const idx = parseInt(m[2])
    ;(draft.value[field] as unknown[])[idx] = patch.updated_value
  }
}

async function saveDraft(): Promise<void> {
  if (!draft.value || !currentSessionId.value) return
  saveLoading.value = true
  try {
    await updateSessionDraft(token(), currentSessionId.value, draft.value)
    message.success('Draft saved')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saveLoading.value = false
  }
}

function proficiencyType(p: string): 'success' | 'warning' | 'default' {
  return p === 'expert' ? 'success' : p === 'intermediate' ? 'warning' : 'default'
}

function reset(): void {
  stage.value = 'jd'
  preview.value = null
  draft.value = null
  draftLoading.value = false
  generateError.value = ''
  selectedExpIndices.value = []
  selectedProjIndices.value = []
  if (currentSessionId.value) {
    try { localStorage.removeItem(_DIAG_PREFIX + currentSessionId.value) } catch { /* ignore */ }
  }
  currentSessionId.value = null
  analyzeError.value = ''
  pendingScope.value = null
  kwDetail.value = null
  sessionJd.value = null
  diagnosticReport.value = null
  draftSnapshot.value = null
  modifiedSections.clear()
  verifiedTaskIds.clear()
  leftActiveTab.value = 'content'
  layoutSettings.value = defaultLayoutSettings()
}
</script>

<style scoped>
/* Stage 1: centered container */
.gen-centered {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px;
}

/* Stage 2: full viewport height, flex column */
.gen-fullscreen {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px); /* minus App header */
  overflow: hidden;
}

.task-card {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
  transition: opacity 0.2s;
}
.task-done {
  opacity: 0.45;
}

/* ── Toolbar ── */
.stage3-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 16px;
  background: #1e1e1e;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
  min-height: 52px;
  flex-wrap: wrap;
}

.toolbar-breadcrumb {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.bc-done {
  font-size: 12px;
  color: #666;
}
.bc-sep {
  font-size: 12px;
  color: #444;
}
.bc-active {
  font-size: 12px;
  font-weight: 600;
  color: #e0e0e0;
}

.toolbar-divider {
  width: 1px;
  height: 28px;
  background: #2a2a2a;
  flex-shrink: 0;
}

.toolbar-scores {
  display: flex;
  align-items: center;
  gap: 8px;
}

.score-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 3px 10px;
  border-radius: 5px;
  background: #151515;
  border: 1px solid #2a2a2a;
  cursor: help;
  min-width: 68px;
  line-height: 1.2;
}
.score-chip.sc-good { border-color: #18a058; }
.score-chip.sc-warn { border-color: #f0a020; }
.score-chip.sc-poor { border-color: #d03050; }

.sc-label {
  font-size: 9px;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
.sc-value {
  font-size: 15px;
  font-weight: 700;
  color: #e0e0e0;
}
.sc-good .sc-value { color: #18a058; }
.sc-warn .sc-value { color: #f0a020; }
.sc-poor .sc-value { color: #d03050; }
.sc-status {
  font-size: 9px;
  color: #666;
}

.toolbar-issues {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background 0.15s;
}
.toolbar-issues:hover {
  background: #2a2a2a;
}

/* ── Split layout ── */
.stage3-split {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.stage3-left {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid #2a2a2a;
}

.stage3-right {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.draft-loading-pane {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 8px;
}

.selection-quote-btn {
  position: fixed;
  z-index: 2000;
  background: #52c41a;
  color: #fff;
  border: none;
  border-radius: 5px;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  transform: translateX(-50%);
  white-space: nowrap;
}
.selection-quote-btn:hover { background: #389e0d; }
</style>

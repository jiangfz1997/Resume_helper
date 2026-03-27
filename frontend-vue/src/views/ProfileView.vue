<template>
  <div>
    <n-page-header title="My Profile" style="margin-bottom: 20px" />

    <n-tabs v-model:value="activeTab" type="line" animated @update:value="onTabChange">

      <!-- ── View ── -->
      <n-tab-pane name="view" tab="View">
        <n-card style="margin-top: 12px">
          <n-button :loading="viewLoading" @click="fetchProfile">Refresh</n-button>
          <template v-if="profile">
            <n-divider />
            <div style="margin-bottom: 20px">
              <n-text style="font-size: 22px; font-weight: 700; display: block">{{ profile.full_name }}</n-text>
              <n-text v-if="profile.summary" depth="2" style="display: block; margin-top: 8px; line-height: 1.7; white-space: pre-wrap">{{ profile.summary }}</n-text>
              <n-text v-else depth="3" style="display: block; margin-top: 8px; font-size: 12px; font-style: italic">No summary yet.</n-text>
            </div>

            <template v-if="profile.work_experiences.length">
              <n-divider title-placement="left">Work Experience</n-divider>
              <n-list>
                <n-list-item v-for="(exp, i) in profile.work_experiences" :key="i">
                  <n-thing :title="`${exp.title} @ ${exp.company}`" :description="`${exp.start_date} — ${exp.end_date ?? 'present'}`">
                    <template #footer>
                      <ul style="margin: 4px 0 0; padding-left: 18px; font-size: 12px; color: #aaa">
                        <li v-for="(d, j) in exp.description" :key="j">{{ d }}</li>
                      </ul>
                    </template>
                  </n-thing>
                </n-list-item>
              </n-list>
            </template>

            <template v-if="profile.educations.length">
              <n-divider title-placement="left">Education</n-divider>
              <n-list>
                <n-list-item v-for="(edu, i) in profile.educations" :key="i">
                  <n-thing
                    :title="`${edu.degree} in ${edu.field_of_study}`"
                    :description="`${edu.institution} · ${edu.start_date} — ${edu.end_date ?? 'present'}${edu.gpa ? ' · GPA ' + edu.gpa : ''}`"
                  />
                </n-list-item>
              </n-list>
            </template>

            <template v-if="profile.projects.length">
              <n-divider title-placement="left">Projects</n-divider>
              <n-list>
                <n-list-item v-for="(proj, i) in profile.projects" :key="i">
                  <n-thing :title="proj.name">
                    <template #description>
                      <template v-if="proj.bullets && proj.bullets.length">
                        <ul style="margin: 4px 0 0; padding-left: 18px; font-size: 12px; color: #aaa">
                          <li v-for="(b, j) in proj.bullets" :key="j">{{ b }}</li>
                        </ul>
                      </template>
                      <span v-else style="font-size: 12px; color: #aaa">{{ proj.description }}</span>
                    </template>
                    <template #footer>
                      <n-space size="small">
                        <n-tag v-for="t in proj.tech_stack" :key="t" size="small" type="info">{{ t }}</n-tag>
                      </n-space>
                    </template>
                  </n-thing>
                </n-list-item>
              </n-list>
            </template>

            <template v-if="profile.skills.length">
              <n-divider title-placement="left">Skills</n-divider>
              <div v-for="(group, cat) in groupedProfileSkills" :key="cat" style="margin-bottom: 10px">
                <n-text depth="2" style="font-size: 12px; font-weight: 600; display: block; margin-bottom: 4px">{{ cat }}</n-text>
                <n-space size="small">
                  <n-tag v-for="s in group" :key="s.name" :type="proficiencyType(s.proficiency)" size="small">{{ s.name }}</n-tag>
                </n-space>
              </div>
            </template>
          </template>
          <n-alert v-if="viewError" type="error" style="margin-top: 12px">{{ viewError }}</n-alert>
        </n-card>
      </n-tab-pane>

      <!-- ── Upload PDF ── -->
      <n-tab-pane name="upload" tab="Upload PDF">
        <n-card style="margin-top: 12px">

          <template v-if="pdfStage === 'pick'">
            <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 16px">
              Upload your existing resume as a PDF. The pipeline will parse and enrich it, then show you a preview before adding it to your profile.
            </n-text>
            <n-upload accept=".pdf" :max="1" :default-upload="false" @change="onFileChange">
              <n-upload-dragger>
                <div style="padding: 24px 0; text-align: center">
                  <n-text style="font-size: 14px">Click or drag a PDF here</n-text>
                  <br />
                  <n-text depth="3" style="font-size: 12px">Only .pdf files are accepted</n-text>
                </div>
              </n-upload-dragger>
            </n-upload>
            <n-space align="center" style="margin-top: 16px">
              <n-button type="primary" :loading="uploadLoading" :disabled="!selectedFile" @click="runUpload">
                Analyze PDF
              </n-button>
              <n-text v-if="selectedFile" depth="3" style="font-size: 12px">
                {{ selectedFile.name }} ({{ (selectedFile.size / 1024).toFixed(0) }} KB)
              </n-text>
            </n-space>
            <n-alert v-if="uploadError" type="error" style="margin-top: 12px">{{ uploadError }}</n-alert>
          </template>

          <template v-if="pdfStage === 'preview' && parsedDraft">
            <n-space justify="space-between" align="center" style="margin-bottom: 16px">
              <n-text style="font-size: 15px; font-weight: 600">Parsed Resume Preview</n-text>
              <n-button size="small" quaternary @click="resetUpload">Re-upload</n-button>
            </n-space>
            <n-alert type="info" style="margin-bottom: 16px">
              Review the extracted data below. Click "Confirm & Add to Profile" to append it to your profile.
            </n-alert>

            <template v-if="parsedDraft.summary">
              <n-divider title-placement="left">Summary</n-divider>
              <n-blockquote>{{ parsedDraft.summary }}</n-blockquote>
            </template>

            <n-divider title-placement="left">Work Experience <n-tag size="tiny" style="margin-left: 8px">{{ parsedDraft.work_experiences.length }}</n-tag></n-divider>
            <n-list v-if="parsedDraft.work_experiences.length">
              <n-list-item v-for="(exp, i) in parsedDraft.work_experiences" :key="i">
                <n-thing :title="`${exp.title} @ ${exp.company}`" :description="`${exp.start_date} — ${exp.end_date ?? 'present'}`">
                  <template #footer>
                    <n-ul style="font-size: 12px; color: #aaa; padding-left: 16px; margin-top: 4px">
                      <li v-for="(d, j) in exp.description" :key="j">{{ d }}</li>
                    </n-ul>
                  </template>
                </n-thing>
              </n-list-item>
            </n-list>
            <n-text v-else depth="3" style="font-size: 12px">None found.</n-text>

            <n-divider title-placement="left">Education <n-tag size="tiny" style="margin-left: 8px">{{ parsedDraft.educations.length }}</n-tag></n-divider>
            <n-list v-if="parsedDraft.educations.length">
              <n-list-item v-for="(edu, i) in parsedDraft.educations" :key="i">
                <n-thing :title="`${edu.degree} in ${edu.field_of_study}`" :description="`${edu.institution} · ${edu.start_date} — ${edu.end_date ?? 'present'}${edu.gpa ? ' · GPA ' + edu.gpa : ''}`" />
              </n-list-item>
            </n-list>
            <n-text v-else depth="3" style="font-size: 12px">None found.</n-text>

            <n-divider title-placement="left">Projects <n-tag size="tiny" style="margin-left: 8px">{{ parsedDraft.projects.length }}</n-tag></n-divider>
            <n-list v-if="parsedDraft.projects.length">
              <n-list-item v-for="(proj, i) in parsedDraft.projects" :key="i">
                <n-thing :title="proj.name">
                  <template #description>
                    <template v-if="proj.bullets && proj.bullets.length">
                      <ul style="margin: 4px 0 0; padding-left: 18px; font-size: 12px; color: #aaa">
                        <li v-for="(b, j) in proj.bullets" :key="j">{{ b }}</li>
                      </ul>
                    </template>
                    <span v-else style="font-size: 12px; color: #aaa">{{ proj.description }}</span>
                  </template>
                  <template #footer>
                    <n-space size="small" style="margin-top: 4px">
                      <n-tag v-for="t in proj.tech_stack" :key="t" size="tiny" type="info">{{ t }}</n-tag>
                    </n-space>
                  </template>
                </n-thing>
              </n-list-item>
            </n-list>
            <n-text v-else depth="3" style="font-size: 12px">None found.</n-text>

            <n-divider title-placement="left">Skills <n-tag size="tiny" style="margin-left: 8px">{{ parsedDraft.skills.length }}</n-tag></n-divider>
            <template v-if="parsedDraft.skills.length">
              <div v-for="(group, cat) in groupedDraftSkills" :key="cat" style="margin-bottom: 10px">
                <n-text depth="2" style="font-size: 12px; font-weight: 600; display: block; margin-bottom: 4px">{{ cat }}</n-text>
                <n-space size="small">
                  <n-tag v-for="s in group" :key="s.name" :type="proficiencyType(s.proficiency)" size="small">{{ s.name }}</n-tag>
                </n-space>
              </div>
            </template>
            <n-text v-else depth="3" style="font-size: 12px">None found.</n-text>

            <n-divider />
            <n-space>
              <n-button type="primary" :loading="confirmLoading" @click="runConfirm">Confirm &amp; Add to Profile</n-button>
              <n-button @click="resetUpload">Re-upload</n-button>
            </n-space>
            <n-alert v-if="confirmError" type="error" style="margin-top: 12px">{{ confirmError }}</n-alert>
          </template>

          <template v-if="pdfStage === 'done'">
            <n-result status="success" title="Profile Updated" description="The parsed resume data has been appended to your profile.">
              <template #footer>
                <n-space>
                  <n-button type="primary" @click="goToView">View Profile</n-button>
                  <n-button @click="resetUpload">Upload Another</n-button>
                </n-space>
              </template>
            </n-result>
          </template>

        </n-card>
      </n-tab-pane>

      <!-- ── Edit ── -->
      <n-tab-pane name="edit" tab="Edit">
        <div @mouseup="onEditMouseUp">
        <n-space vertical size="medium" style="margin-top: 12px">

          <!-- Basic Info -->
          <n-card title="Basic Info">
            <n-form-item label="Full Name" label-placement="top" :show-feedback="false">
              <n-input v-model:value="editData.full_name" placeholder="Your full name" />
            </n-form-item>
          </n-card>

          <!-- Summary -->
          <n-card title="Summary">
            <template #header-extra>
              <n-button size="tiny" quaternary @click="openChatForSummary">AI Edit</n-button>
            </template>
            <n-input v-model:value="editData.summary" type="textarea" :rows="3" placeholder="Professional summary..." />
          </n-card>

          <!-- Work Experience -->
          <n-card title="Work Experience">
            <template #header-extra>
              <n-button size="tiny" quaternary @click="openChatForExp(-1)">AI Edit</n-button>
            </template>
            <n-button dashed size="small" style="margin-bottom: 16px" @click="addExp">+ Add Experience</n-button>
            <n-collapse>
              <n-collapse-item
                v-for="(exp, i) in editData.work_experiences"
                :key="i"
                :name="String(i)"
              >
                <template #header>
                  <n-space align="center" size="small" style="flex: 1; min-width: 0">
                    <n-text style="font-size: 13px; font-weight: 500">
                      {{ exp.title || '(new)' }}<span v-if="exp.company"> @ {{ exp.company }}</span>
                    </n-text>
                    <n-text depth="3" style="font-size: 12px">{{ exp.start_date }}</n-text>
                  </n-space>
                </template>
                <template #header-extra>
                  <n-button size="tiny" quaternary style="margin-right: 4px" @click.stop="openChatForExp(i)">AI Edit</n-button>
                  <n-button size="tiny" type="error" quaternary @click.stop="removeExp(i)">Delete</n-button>
                </template>

                <n-grid :cols="3" :x-gap="12" :y-gap="8" style="margin-bottom: 12px">
                  <n-gi>
                    <n-form-item label="Title" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="exp.title" size="small" />
                    </n-form-item>
                  </n-gi>
                  <n-gi>
                    <n-form-item label="Company" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="exp.company" size="small" />
                    </n-form-item>
                  </n-gi>
                  <n-gi>
                    <n-form-item label="Start Date" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="exp.start_date" size="small" placeholder="YYYY-MM" />
                    </n-form-item>
                  </n-gi>
                  <n-gi>
                    <n-form-item label="End Date" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="exp.end_date" size="small" placeholder="YYYY-MM or leave blank" />
                    </n-form-item>
                  </n-gi>
                </n-grid>

                <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 6px">BULLET POINTS</n-text>
                <n-space vertical size="small">
                  <div v-for="(bullet, bi) in exp.description" :key="bi" style="display: flex; gap: 8px; align-items: flex-start">
                    <n-input
                      v-model:value="exp.description[bi]"
                      type="textarea"
                      :rows="2"
                      :autosize="{ minRows: 1, maxRows: 4 }"
                      size="small"
                      style="flex: 1"
                    />
                    <n-button size="tiny" quaternary type="error" style="margin-top: 4px; flex-shrink: 0" @click="exp.description.splice(bi, 1)">Del</n-button>
                  </div>
                  <n-button size="tiny" dashed @click="exp.description.push('')">+ Add bullet</n-button>
                </n-space>
              </n-collapse-item>
            </n-collapse>
            <n-text v-if="!editData.work_experiences.length" depth="3" style="font-size: 12px">No experiences yet.</n-text>
          </n-card>

          <!-- Education -->
          <n-card title="Education">
            <template #header-extra>
              <n-button size="tiny" quaternary @click="openChatForEdu(-1)">AI Edit</n-button>
            </template>
            <n-button dashed size="small" style="margin-bottom: 16px" @click="addEdu">+ Add Education</n-button>
            <n-collapse>
              <n-collapse-item
                v-for="(edu, i) in editData.educations"
                :key="i"
                :name="String(i)"
              >
                <template #header>
                  <n-space align="center" size="small">
                    <n-text style="font-size: 13px; font-weight: 500">
                      {{ edu.degree || '(new)' }}<span v-if="edu.institution"> — {{ edu.institution }}</span>
                    </n-text>
                  </n-space>
                </template>
                <template #header-extra>
                  <n-button size="tiny" quaternary style="margin-right: 4px" @click.stop="openChatForEdu(i)">AI Edit</n-button>
                  <n-button size="tiny" type="error" quaternary @click.stop="removeEdu(i)">Delete</n-button>
                </template>

                <n-grid :cols="3" :x-gap="12" :y-gap="8">
                  <n-gi>
                    <n-form-item label="Institution" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="edu.institution" size="small" />
                    </n-form-item>
                  </n-gi>
                  <n-gi>
                    <n-form-item label="Degree" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="edu.degree" size="small" />
                    </n-form-item>
                  </n-gi>
                  <n-gi>
                    <n-form-item label="Field of Study" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="edu.field_of_study" size="small" />
                    </n-form-item>
                  </n-gi>
                  <n-gi>
                    <n-form-item label="Start Date" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="edu.start_date" size="small" placeholder="YYYY-MM" />
                    </n-form-item>
                  </n-gi>
                  <n-gi>
                    <n-form-item label="End Date" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="edu.end_date" size="small" placeholder="YYYY-MM" />
                    </n-form-item>
                  </n-gi>
                  <n-gi>
                    <n-form-item label="GPA" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="edu.gpa" size="small" placeholder="optional" />
                    </n-form-item>
                  </n-gi>
                </n-grid>
              </n-collapse-item>
            </n-collapse>
            <n-text v-if="!editData.educations.length" depth="3" style="font-size: 12px">No education records yet.</n-text>
          </n-card>

          <!-- Projects -->
          <n-card title="Projects">
            <template #header-extra>
              <n-button size="tiny" quaternary @click="openChatForProj(-1)">AI Edit</n-button>
            </template>
            <n-button dashed size="small" style="margin-bottom: 16px" @click="addProj">+ Add Project</n-button>
            <n-collapse>
              <n-collapse-item
                v-for="(proj, i) in editData.projects"
                :key="i"
                :name="String(i)"
              >
                <template #header>
                  <n-text style="font-size: 13px; font-weight: 500">{{ proj.name || '(new)' }}</n-text>
                </template>
                <template #header-extra>
                  <n-button size="tiny" quaternary style="margin-right: 4px" @click.stop="openChatForProj(i)">AI Edit</n-button>
                  <n-button size="tiny" type="error" quaternary @click.stop="removeProj(i)">Delete</n-button>
                </template>

                <n-grid :cols="2" :x-gap="12" :y-gap="8" style="margin-bottom: 12px">
                  <n-gi>
                    <n-form-item label="Name" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="proj.name" size="small" />
                    </n-form-item>
                  </n-gi>
                  <n-gi>
                    <n-form-item label="URL" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="proj.url" size="small" placeholder="optional" />
                    </n-form-item>
                  </n-gi>
                  <n-gi :span="2">
                    <n-form-item label="Description (summary)" label-placement="top" :show-feedback="false">
                      <n-input v-model:value="proj.description" type="textarea" :rows="2" size="small" />
                    </n-form-item>
                  </n-gi>
                </n-grid>

                <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 6px">TECH STACK</n-text>
                <n-space size="small" style="flex-wrap: wrap; margin-bottom: 10px">
                  <n-tag v-for="(tech, ti) in proj.tech_stack" :key="ti" size="small" closable @close="proj.tech_stack.splice(ti, 1)">{{ tech }}</n-tag>
                  <n-input
                    v-model:value="techInputs[i]"
                    size="tiny"
                    placeholder="Add tech..."
                    style="width: 100px"
                    @keydown.enter.prevent="addTech(i)"
                  />
                </n-space>

                <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 6px">BULLET POINTS</n-text>
                <n-space vertical size="small">
                  <div v-for="(bullet, bi) in proj.bullets" :key="bi" style="display: flex; gap: 8px; align-items: flex-start">
                    <n-input
                      v-model:value="proj.bullets[bi]"
                      type="textarea"
                      :rows="2"
                      :autosize="{ minRows: 1, maxRows: 4 }"
                      size="small"
                      style="flex: 1"
                    />
                    <n-button size="tiny" quaternary type="error" style="margin-top: 4px; flex-shrink: 0" @click="proj.bullets.splice(bi, 1)">Del</n-button>
                  </div>
                  <n-button size="tiny" dashed @click="proj.bullets.push('')">+ Add bullet</n-button>
                </n-space>
              </n-collapse-item>
            </n-collapse>
            <n-text v-if="!editData.projects.length" depth="3" style="font-size: 12px">No projects yet.</n-text>
          </n-card>

          <!-- Skills -->
          <n-card title="Skills">
            <template #header-extra>
              <n-button size="tiny" quaternary @click="openChatForSkills">AI Edit</n-button>
            </template>
            <n-space align="center" style="margin-bottom: 14px">
              <n-text depth="3" style="font-size: 12px">{{ editData.skills.length }} skills</n-text>
              <template v-if="!skillSelectMode">
                <n-button size="small" quaternary @click="skillSelectMode = true; selectedSkillIndices = []">Select</n-button>
                <n-popconfirm
                  v-if="editData.skills.length"
                  :positive-text="`Delete all ${editData.skills.length}`"
                  negative-text="Cancel"
                  @positive-click="clearAllSkills"
                >
                  <template #trigger>
                    <n-button size="small" type="error" quaternary>Clear All</n-button>
                  </template>
                  Delete all {{ editData.skills.length }} skills and save immediately?
                </n-popconfirm>
              </template>
              <template v-else>
                <n-button
                  size="small"
                  quaternary
                  @click="selectedSkillIndices = editData.skills.map((_, i) => i)"
                >
                  Select All
                </n-button>
                <n-button
                  size="small"
                  type="error"
                  :disabled="selectedSkillIndices.length === 0"
                  @click="deleteSelectedSkills"
                >
                  Delete ({{ selectedSkillIndices.length }})
                </n-button>
                <n-button size="small" quaternary @click="exitSkillSelect">Cancel</n-button>
              </template>
            </n-space>

            <template v-if="editData.skills.length">
              <div
                v-for="(group, cat) in editGroupedSkills"
                :key="cat"
                style="margin-bottom: 14px"
              >
                <n-text
                  depth="2"
                  style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 6px"
                >
                  {{ cat }}
                </n-text>
                <n-space size="small" style="flex-wrap: wrap">
                  <n-tag
                    v-for="sk in group"
                    :key="sk._idx"
                    :type="selectedSkillIndices.includes(sk._idx) ? 'error' : proficiencyType(sk.proficiency)"
                    size="small"
                    :closable="!skillSelectMode"
                    :style="skillSelectMode ? 'cursor:pointer' : ''"
                    @close.stop="editData.skills.splice(sk._idx, 1)"
                    @click="skillSelectMode ? toggleSkillSelect(sk._idx) : undefined"
                  >
                    <template v-if="skillSelectMode" #icon>
                      <n-checkbox
                        :checked="selectedSkillIndices.includes(sk._idx)"
                        size="small"
                        style="pointer-events: none"
                      />
                    </template>
                    {{ sk.name }}
                  </n-tag>
                </n-space>
              </div>
            </template>
            <n-text v-else depth="3" style="font-size: 12px">No skills yet.</n-text>

            <n-divider style="margin: 12px 0" />
            <n-space align="center" size="small" style="flex-wrap: wrap">
              <n-input
                v-model:value="newSkillInput.category"
                placeholder="Category"
                size="small"
                style="width: 120px"
              />
              <n-input
                v-model:value="newSkillInput.name"
                placeholder="Skill name"
                size="small"
                style="width: 150px"
                @keydown.enter.prevent="confirmAddSkill"
              />
              <n-select
                v-model:value="newSkillInput.proficiency"
                :options="proficiencyOptions"
                size="small"
                style="width: 130px"
              />
              <n-button size="small" type="primary" @click="confirmAddSkill">Add</n-button>
            </n-space>
          </n-card>

          <n-alert v-if="editError" type="error">{{ editError }}</n-alert>
          <n-alert v-if="editSuccess" type="success">{{ editSuccess }}</n-alert>
          <n-button type="primary" :loading="editLoading" @click="saveEdit">Save Profile</n-button>

        </n-space>
        </div>
      </n-tab-pane>

      <!-- ── Base Resume ── -->
      <n-tab-pane name="base" tab="Base Resume">
        <n-card style="margin-top: 12px">
          <template v-if="!baseResume">
            <n-space vertical size="medium" style="align-items: flex-start">
              <n-text depth="3" style="font-size: 13px; line-height: 1.6">
                Generate a polished base resume from your profile. This will be used as the
                starting point for every JD-specific tailoring — the AI will only make
                targeted adjustments instead of generating from scratch.
              </n-text>
              <n-alert v-if="!profile?.work_experiences?.length" type="warning" style="width: 100%">
                Your profile has no work experience yet. Upload a PDF or add experience in the
                Edit tab first.
              </n-alert>
              <n-button
                type="primary"
                :loading="baseGenLoading"
                :disabled="!profile?.work_experiences?.length"
                @click="runGenerateBase"
              >
                Generate Base Resume
              </n-button>
              <n-alert v-if="baseGenError" type="error">{{ baseGenError }}</n-alert>
            </n-space>
          </template>

          <template v-else>
            <n-space justify="space-between" align="center" style="margin-bottom: 16px">
              <n-text style="font-weight: 600">Base Resume</n-text>
              <n-space size="small">
                <n-button size="small" quaternary :loading="baseGenLoading" @click="runGenerateBase">
                  Regenerate
                </n-button>
                <n-button size="small" type="primary" :loading="baseSaveLoading" @click="runSaveBase">
                  Save Changes
                </n-button>
              </n-space>
            </n-space>

            <n-alert type="info" style="margin-bottom: 16px; font-size: 12px">
              This is your editable base resume. Changes here persist to your profile and will be
              used as the starting point for all future JD tailoring.
            </n-alert>

            <!-- Summary -->
            <n-divider title-placement="left">Summary</n-divider>
            <n-input
              v-model:value="baseResume.summary"
              type="textarea"
              :rows="3"
              :autosize="{ minRows: 2, maxRows: 6 }"
            />

            <!-- Experiences -->
            <n-divider title-placement="left">
              Work Experience
              <n-tag size="tiny" style="margin-left: 8px">{{ baseResume.experiences.length }}</n-tag>
            </n-divider>
            <n-collapse>
              <n-collapse-item
                v-for="(exp, i) in baseResume.experiences"
                :key="i"
                :name="String(i)"
              >
                <template #header>
                  <n-text style="font-size: 13px; font-weight: 500">
                    {{ exp.title || '(new)' }}<span v-if="exp.company"> @ {{ exp.company }}</span>
                  </n-text>
                </template>
                <n-space vertical size="small">
                  <div
                    v-for="(bullet, bi) in exp.bullets"
                    :key="bi"
                    style="display: flex; gap: 8px; align-items: flex-start"
                  >
                    <n-input
                      v-model:value="exp.bullets[bi].text"
                      type="textarea"
                      :rows="2"
                      :autosize="{ minRows: 1, maxRows: 4 }"
                      size="small"
                      style="flex: 1"
                    />
                    <n-button
                      size="tiny"
                      quaternary
                      type="error"
                      style="margin-top: 4px; flex-shrink: 0"
                      @click="exp.bullets.splice(bi, 1)"
                    >
                      Del
                    </n-button>
                  </div>
                  <n-button size="tiny" dashed @click="exp.bullets.push({ text: '', highlighted: false })">
                    + Add bullet
                  </n-button>
                </n-space>
              </n-collapse-item>
            </n-collapse>

            <!-- Projects -->
            <n-divider title-placement="left">
              Projects
              <n-tag size="tiny" style="margin-left: 8px">{{ baseResume.projects.length }}</n-tag>
            </n-divider>
            <n-collapse>
              <n-collapse-item
                v-for="(proj, i) in baseResume.projects"
                :key="i"
                :name="`proj-${i}`"
              >
                <template #header>
                  <n-text style="font-size: 13px; font-weight: 500">{{ proj.name }}</n-text>
                </template>
                <n-space vertical size="small">
                  <div
                    v-for="(bullet, bi) in proj.bullets"
                    :key="bi"
                    style="display: flex; gap: 8px; align-items: flex-start"
                  >
                    <n-input
                      v-model:value="proj.bullets[bi].text"
                      type="textarea"
                      :rows="2"
                      :autosize="{ minRows: 1, maxRows: 4 }"
                      size="small"
                      style="flex: 1"
                    />
                    <n-button
                      size="tiny"
                      quaternary
                      type="error"
                      style="margin-top: 4px; flex-shrink: 0"
                      @click="proj.bullets.splice(bi, 1)"
                    >
                      Del
                    </n-button>
                  </div>
                  <n-button size="tiny" dashed @click="proj.bullets.push({ text: '', highlighted: false })">
                    + Add bullet
                  </n-button>
                </n-space>
              </n-collapse-item>
            </n-collapse>

            <n-alert v-if="baseSaveError" type="error" style="margin-top: 12px">{{ baseSaveError }}</n-alert>
            <n-alert v-if="baseSaveSuccess" type="success" style="margin-top: 12px">{{ baseSaveSuccess }}</n-alert>
          </template>
        </n-card>
      </n-tab-pane>

    </n-tabs>
  </div>

  <button
    v-if="selectionBtn"
    ref="quoteButtonRef"
    class="selection-quote-btn"
    :style="{ left: selectionBtn.x + 'px', top: (selectionBtn.y - 38) + 'px' }"
    @click="quoteSelection"
  >
    Quote
  </button>

  <ProfileChatPanel ref="profileChatPanelRef" @patch="applyProfilePatch" />
</template>

<script setup lang="ts">
import type { SelectOption, UploadFileInfo } from 'naive-ui'
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

type IndexedSkill = Skill & { _idx: number }
import {
  confirmParsedDraft,
  generateBaseResume,
  getProfile,
  replaceSkills,
  saveBaseResume,
  updateProfile as apiUpdateProfile,
  updateUserMe,
  uploadResumePDF,
} from '../api/client'
import type { Education, MasterProfile, ParsedProfileDraft, ProficiencyLevel, Project, Skill, TailoredResumeDraft, WorkExperience } from '../api/client'
import { useAuthStore } from '../stores/auth'
import ProfileChatPanel from '../components/ProfileChatPanel.vue'
import type { ProfileChatInit } from '../components/ProfileChatPanel.vue'

const auth = useAuthStore()
const token = () => auth.token!
const activeTab = ref('view')

function proficiencyType(p: ProficiencyLevel): 'success' | 'warning' | 'default' {
  return p === 'expert' ? 'success' : p === 'intermediate' ? 'warning' : 'default'
}

function groupSkills(skills: Skill[]): Record<string, Skill[]> {
  return skills.reduce<Record<string, Skill[]>>((acc, s) => {
    ;(acc[s.category] ??= []).push(s)
    return acc
  }, {})
}

const groupedProfileSkills = computed(() =>
  profile.value ? groupSkills(profile.value.skills) : {}
)

const groupedDraftSkills = computed(() =>
  parsedDraft.value ? groupSkills(parsedDraft.value.skills) : {}
)

// ── view ───────────────────────────────────────────────────────
const profile = ref<MasterProfile | null>(null)
const viewLoading = ref(false)
const viewError = ref('')

async function fetchProfile(): Promise<void> {
  viewLoading.value = true
  viewError.value = ''
  try {
    profile.value = await getProfile(token())
    if (profile.value.base_resume && !baseResume.value) {
      baseResume.value = JSON.parse(JSON.stringify(profile.value.base_resume))
    }
  } catch (e) {
    viewError.value = (e as Error).message
  } finally {
    viewLoading.value = false
  }
}

onMounted(() => {
  fetchProfile()
  document.addEventListener('mousedown', onDocMouseDown)
})

// ── upload pdf ─────────────────────────────────────────────────
type PdfStage = 'pick' | 'preview' | 'done'
const pdfStage = ref<PdfStage>('pick')
const selectedFile = ref<File | null>(null)
const parsedDraft = ref<ParsedProfileDraft | null>(null)
const uploadLoading = ref(false)
const uploadError = ref('')
const confirmLoading = ref(false)
const confirmError = ref('')

function onFileChange(data: { fileList: UploadFileInfo[] }): void {
  const info = data.fileList[0]
  selectedFile.value = info?.file ?? null
  uploadError.value = ''
}

async function runUpload(): Promise<void> {
  if (!selectedFile.value) return
  uploadError.value = ''
  uploadLoading.value = true
  try {
    parsedDraft.value = await uploadResumePDF(token(), selectedFile.value)
    pdfStage.value = 'preview'
  } catch (e) {
    uploadError.value = (e as Error).message
  } finally {
    uploadLoading.value = false
  }
}

async function runConfirm(): Promise<void> {
  if (!parsedDraft.value) return
  confirmError.value = ''
  confirmLoading.value = true
  try {
    await confirmParsedDraft(token(), parsedDraft.value)
    pdfStage.value = 'done'
    await fetchProfile()
  } catch (e) {
    confirmError.value = (e as Error).message
  } finally {
    confirmLoading.value = false
  }
}

function resetUpload(): void {
  pdfStage.value = 'pick'
  selectedFile.value = null
  parsedDraft.value = null
  uploadError.value = ''
  confirmError.value = ''
}

function goToView(): void {
  activeTab.value = 'view'
}

// ── edit ───────────────────────────────────────────────────────
interface EditData {
  full_name: string
  summary: string
  work_experiences: WorkExperience[]
  educations: Education[]
  projects: Project[]
  skills: Skill[]
}

const editData = reactive<EditData>({
  full_name: '',
  summary: '',
  work_experiences: [],
  educations: [],
  projects: [],
  skills: [],
})

const techInputs = ref<string[]>([])
const editLoading = ref(false)
const editError = ref('')
const editSuccess = ref('')

function populateEdit(): void {
  if (!profile.value) return
  editData.full_name = profile.value.full_name
  editData.summary = profile.value.summary ?? ''
  editData.work_experiences = profile.value.work_experiences.map(e => ({
    ...e,
    description: [...e.description],
    end_date: e.end_date ?? '',
  }))
  editData.educations = profile.value.educations.map(e => ({
    ...e,
    end_date: e.end_date ?? '',
    gpa: e.gpa ?? '',
  }))
  editData.projects = profile.value.projects.map(p => ({
    ...p,
    tech_stack: [...p.tech_stack],
    bullets: [...(p.bullets ?? [])],
    url: p.url ?? '',
  }))
  techInputs.value = editData.projects.map(() => '')
  editData.skills = profile.value.skills.map(s => ({ ...s }))
}

function addExp(): void {
  editData.work_experiences.unshift({ company: '', title: '', start_date: '', end_date: '', description: [] })
}

function removeExp(i: number): void {
  editData.work_experiences.splice(i, 1)
}

function addEdu(): void {
  editData.educations.unshift({ institution: '', degree: '', field_of_study: '', start_date: '', end_date: '', gpa: '' })
}

function removeEdu(i: number): void {
  editData.educations.splice(i, 1)
}

function addProj(): void {
  editData.projects.unshift({ name: '', description: '', bullets: [], tech_stack: [], url: '' })
  techInputs.value.unshift('')
}

function removeProj(i: number): void {
  editData.projects.splice(i, 1)
  techInputs.value.splice(i, 1)
}

// skill multi-select
const skillSelectMode = ref(false)
const selectedSkillIndices = ref<number[]>([])

const editGroupedSkills = computed<Record<string, IndexedSkill[]>>(() => {
  const map: Record<string, IndexedSkill[]> = {}
  editData.skills.forEach((s, i) => {
    const cat = s.category.trim() || 'Uncategorized'
    ;(map[cat] ??= []).push({ ...s, _idx: i })
  })
  return map
})

function toggleSkillSelect(idx: number): void {
  const pos = selectedSkillIndices.value.indexOf(idx)
  if (pos === -1) selectedSkillIndices.value.push(idx)
  else selectedSkillIndices.value.splice(pos, 1)
}

function exitSkillSelect(): void {
  skillSelectMode.value = false
  selectedSkillIndices.value = []
}

function deleteSelectedSkills(): void {
  const sorted = [...selectedSkillIndices.value].sort((a, b) => b - a)
  sorted.forEach((i) => editData.skills.splice(i, 1))
  exitSkillSelect()
}

async function clearAllSkills(): Promise<void> {
  editData.skills = []
  editError.value = ''
  editSuccess.value = ''
  try {
    await replaceSkills(token(), [])
    editSuccess.value = 'All skills deleted.'
    await fetchProfile()
  } catch (e) {
    editError.value = (e as Error).message
  }
}

// inline add
const newSkillInput = reactive<Skill>({ category: '', name: '', proficiency: 'intermediate' })

function confirmAddSkill(): void {
  if (!newSkillInput.category.trim() || !newSkillInput.name.trim()) return
  editData.skills.push({ ...newSkillInput })
  newSkillInput.name = ''
}

function addEditSkill(): void {
  editData.skills.unshift({ category: '', name: '', proficiency: 'intermediate' })
}

function addTech(i: number): void {
  const val = techInputs.value[i]?.trim()
  if (val) {
    editData.projects[i].tech_stack.push(val)
    techInputs.value[i] = ''
  }
}

async function saveEdit(): Promise<void> {
  editError.value = ''
  editSuccess.value = ''
  editLoading.value = true
  try {
    if (editData.full_name.trim() && editData.full_name !== profile.value?.full_name) {
      await updateUserMe(token(), { full_name: editData.full_name.trim() })
    }
    await apiUpdateProfile(token(), {
      summary: editData.summary || undefined,
      work_experiences: editData.work_experiences.map(e => ({
        ...e,
        end_date: e.end_date || undefined,
        description: e.description.filter(d => d.trim()),
      })),
      educations: editData.educations.map(e => ({
        ...e,
        end_date: e.end_date || undefined,
        gpa: e.gpa || undefined,
      })),
      projects: editData.projects.map(p => ({
        ...p,
        url: p.url || undefined,
        bullets: p.bullets.filter(b => b.trim()),
      })),
    })
    const validSkills = editData.skills.filter(s => s.category.trim() && s.name.trim())
    await replaceSkills(token(), validSkills)
    editSuccess.value = 'Profile saved.'
    await fetchProfile()
  } catch (e) {
    editError.value = (e as Error).message
  } finally {
    editLoading.value = false
  }
}

const proficiencyOptions: SelectOption[] = [
  { label: 'Expert', value: 'expert' },
  { label: 'Intermediate', value: 'intermediate' },
  { label: 'Beginner', value: 'beginner' },
]

// ── base resume ────────────────────────────────────────────────
const baseResume = ref<TailoredResumeDraft | null>(null)
const baseGenLoading = ref(false)
const baseGenError = ref('')
const baseSaveLoading = ref(false)
const baseSaveError = ref('')
const baseSaveSuccess = ref('')

function onTabChange(tab: string): void {
  if (tab === 'edit') populateEdit()
  if (tab === 'base' && profile.value?.base_resume) {
    baseResume.value = JSON.parse(JSON.stringify(profile.value.base_resume))
  }
}

async function runGenerateBase(): Promise<void> {
  baseGenError.value = ''
  baseGenLoading.value = true
  try {
    baseResume.value = await generateBaseResume(token())
    await fetchProfile()
  } catch (e) {
    baseGenError.value = (e as Error).message
  } finally {
    baseGenLoading.value = false
  }
}

async function runSaveBase(): Promise<void> {
  if (!baseResume.value) return
  baseSaveError.value = ''
  baseSaveSuccess.value = ''
  baseSaveLoading.value = true
  try {
    await saveBaseResume(token(), baseResume.value)
    baseSaveSuccess.value = 'Base resume saved.'
    await fetchProfile()
  } catch (e) {
    baseSaveError.value = (e as Error).message
  } finally {
    baseSaveLoading.value = false
  }
}

// ── text selection quote ────────────────────────────────────────
interface SelectionBtn {
  x: number
  y: number
  text: string
}
const selectionBtn = ref<SelectionBtn | null>(null)
const quoteButtonRef = ref<HTMLElement | null>(null)

function onEditMouseUp(e: MouseEvent): void {
  const target = e.target as HTMLElement
  if (!(target instanceof HTMLTextAreaElement)) return
  const start = target.selectionStart ?? 0
  const end = target.selectionEnd ?? 0
  if (start === end) {
    selectionBtn.value = null
    return
  }
  const text = target.value.substring(start, end).trim()
  if (!text) {
    selectionBtn.value = null
    return
  }
  selectionBtn.value = { x: e.clientX, y: e.clientY, text }
}

function quoteSelection(): void {
  if (!selectionBtn.value) return
  profileChatPanelRef.value?.openWithSelection(selectionBtn.value.text)
  selectionBtn.value = null
}

function onDocMouseDown(e: MouseEvent): void {
  if (quoteButtonRef.value && quoteButtonRef.value.contains(e.target as Node)) return
  selectionBtn.value = null
}

onUnmounted(() => {
  document.removeEventListener('mousedown', onDocMouseDown)
})

// ── profile AI chat ─────────────────────────────────────────────
const profileChatPanelRef = ref<InstanceType<typeof ProfileChatPanel> | null>(null)

function openChatForSummary(): void {
  profileChatPanelRef.value?.open({
    scope: { path: 'summary', label: 'Summary' },
    sectionType: 'summary',
    sectionIndex: undefined,
    sectionData: editData.summary,
  })
}

function openChatForExp(i: number): void {
  if (i < 0) {
    profileChatPanelRef.value?.open({
      scope: { path: 'work_experiences', label: 'Work Experience' },
      sectionType: 'work_experiences',
      sectionIndex: undefined,
      sectionData: editData.work_experiences,
    })
    return
  }
  const exp = editData.work_experiences[i]
  profileChatPanelRef.value?.open({
    scope: { path: `work_experiences[${i}]`, label: `${exp.title || 'Experience'} @ ${exp.company || '?'}` },
    sectionType: 'work_experiences',
    sectionIndex: i,
    sectionData: JSON.parse(JSON.stringify(exp)),
  })
}

function openChatForEdu(i: number): void {
  if (i < 0) {
    profileChatPanelRef.value?.open({
      scope: { path: 'educations', label: 'Education' },
      sectionType: 'educations',
      sectionIndex: undefined,
      sectionData: editData.educations,
    })
    return
  }
  const edu = editData.educations[i]
  profileChatPanelRef.value?.open({
    scope: { path: `educations[${i}]`, label: `${edu.degree || 'Education'} — ${edu.institution || '?'}` },
    sectionType: 'educations',
    sectionIndex: i,
    sectionData: JSON.parse(JSON.stringify(edu)),
  })
}

function openChatForProj(i: number): void {
  if (i < 0) {
    profileChatPanelRef.value?.open({
      scope: { path: 'projects', label: 'Projects' },
      sectionType: 'projects',
      sectionIndex: undefined,
      sectionData: editData.projects,
    })
    return
  }
  const proj = editData.projects[i]
  profileChatPanelRef.value?.open({
    scope: { path: `projects[${i}]`, label: proj.name || 'Project' },
    sectionType: 'projects',
    sectionIndex: i,
    sectionData: JSON.parse(JSON.stringify(proj)),
  })
}

function openChatForSkills(): void {
  profileChatPanelRef.value?.open({
    scope: { path: 'skills', label: 'Skills' },
    sectionType: 'skills',
    sectionIndex: undefined,
    sectionData: JSON.parse(JSON.stringify(editData.skills)),
  })
}

function applyProfilePatch(path: string, updatedValue: unknown): void {
  if (path === 'summary') {
    editData.summary = updatedValue as string
    return
  }
  const m = path.match(/^(\w+)\[(\d+)\]$/)
  if (m) {
    const field = m[1] as 'work_experiences' | 'educations' | 'projects'
    const idx = parseInt(m[2])
    if (field === 'work_experiences' && idx < editData.work_experiences.length) {
      Object.assign(editData.work_experiences[idx], updatedValue)
    } else if (field === 'educations' && idx < editData.educations.length) {
      Object.assign(editData.educations[idx], updatedValue)
    } else if (field === 'projects' && idx < editData.projects.length) {
      Object.assign(editData.projects[idx], updatedValue)
    }
    return
  }
  if (path === 'skills' && Array.isArray(updatedValue)) {
    editData.skills = updatedValue as Skill[]
  }
}
</script>

<style scoped>
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

.selection-quote-btn:hover {
  background: #389e0d;
}
</style>

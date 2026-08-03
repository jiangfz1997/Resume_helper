from app.agents.profile_parser import _Header, _SectionHeaders, TwoPhaseProfileParser
from app.api.routes.profile import _join_wrapped_lines

RIGHT_MARGIN = 500.0


def _split(lines: list[str], headers: list[_Header]) -> list:
    return TwoPhaseProfileParser._split_sections(lines, _SectionHeaders(headers=headers))


class TestSplitSections:
    """A projects block must never leak into the experience block above it."""

    LINES = [
        "EXPERIENCE",
        "Netease Games",
        "Designed and automated end-to-end API testing pipelines.",
        "RELATED PROJECTS",
        "AI-Powered Resume Generation System",
        "Built a JD-aware multi-agent resume platform.",
        "EDUCATION",
        "University of Western Ontario",
    ]

    def test_correctly_labelled_projects_header_bounds_experience(self) -> None:
        sections = _split(
            self.LINES,
            [
                _Header(index=0, text="EXPERIENCE", kind="experience"),
                _Header(index=3, text="RELATED PROJECTS", kind="projects"),
                _Header(index=6, text="EDUCATION", kind="education"),
            ],
        )
        merged = TwoPhaseProfileParser._merge_by_kind(sections)
        assert "RELATED PROJECTS" not in merged["experience"]
        assert "AI-Powered" not in merged["experience"]
        assert "AI-Powered" in merged["projects"]

    def test_header_labelled_other_still_bounds_experience(self) -> None:
        """The regression that shipped: a missed label must not contaminate."""
        sections = _split(
            self.LINES,
            [
                _Header(index=0, text="EXPERIENCE", kind="experience"),
                _Header(index=3, text="RELATED PROJECTS", kind="other"),
                _Header(index=6, text="EDUCATION", kind="education"),
            ],
        )
        merged = TwoPhaseProfileParser._merge_by_kind(sections)
        assert "AI-Powered" not in merged["experience"]

    def test_other_header_with_mappable_wording_is_rescued(self) -> None:
        sections = _split(
            self.LINES,
            [
                _Header(index=0, text="EXPERIENCE", kind="experience"),
                _Header(index=3, text="RELATED PROJECTS", kind="other"),
            ],
        )
        assert [s.kind for s in sections] == ["experience", "projects"]

    def test_genuinely_other_header_is_not_rescued(self) -> None:
        sections = _split(
            ["EXPERIENCE", "Netease Games", "AWARDS", "Dean's List 2024"],
            [
                _Header(index=0, text="EXPERIENCE", kind="experience"),
                _Header(index=2, text="AWARDS", kind="other"),
            ],
        )
        assert [s.kind for s in sections] == ["experience", "other"]
        assert TwoPhaseProfileParser._merge_by_kind(sections).get("other") is None

    def test_repeated_kind_is_merged_in_document_order(self) -> None:
        sections = _split(
            ["PROJECTS", "Alpha", "SIDE PROJECTS", "Beta"],
            [
                _Header(index=0, text="PROJECTS", kind="projects"),
                _Header(index=2, text="SIDE PROJECTS", kind="projects"),
            ],
        )
        assert TwoPhaseProfileParser._merge_by_kind(sections)["projects"] == "Alpha\nBeta"

    def test_out_of_range_index_is_ignored(self) -> None:
        sections = _split(
            ["EXPERIENCE", "Netease Games"],
            [
                _Header(index=0, text="EXPERIENCE", kind="experience"),
                _Header(index=99, text="PROJECTS", kind="projects"),
            ],
        )
        assert [s.kind for s in sections] == ["experience"]

    def test_no_headers_yields_no_sections(self) -> None:
        assert _split(["Some text"], []) == []


class TestJoinWrappedLines:
    """Renderer-wrapped bullets must be rebuilt regardless of capitalisation."""

    def test_capitalised_continuation_is_joined(self) -> None:
        lines = [
            ("• Deployed on Kubernetes over AWS EC2; built and rolled out via GitHub", 498.0),
            ("Actions with OIDC to ECR.", 260.0),
        ]
        assert _join_wrapped_lines(lines, RIGHT_MARGIN) == [
            "• Deployed on Kubernetes over AWS EC2; built and rolled out via GitHub "
            "Actions with OIDC to ECR."
        ]

    def test_slash_continuation_is_joined(self) -> None:
        lines = [
            ("• Built a distributed IM backend with a Redis routing table with", 495.0),
            ("Pub/Sub for targeted cross-node message delivery.", 300.0),
        ]
        assert len(_join_wrapped_lines(lines, RIGHT_MARGIN)) == 1

    def test_short_line_does_not_absorb_the_next(self) -> None:
        lines = [("EXPERIENCE", 120.0), ("Netease Games", 200.0)]
        assert _join_wrapped_lines(lines, RIGHT_MARGIN) == ["EXPERIENCE", "Netease Games"]

    def test_bullet_always_starts_a_new_line(self) -> None:
        lines = [
            ("• First bullet running all the way to the right hand margin here", 499.0),
            ("• Second bullet", 180.0),
        ]
        assert len(_join_wrapped_lines(lines, RIGHT_MARGIN)) == 2

    def test_whitespace_is_collapsed_and_blanks_dropped(self) -> None:
        lines = [("  Netease   Games  ", 200.0), ("   ", 0.0), ("Toronto", 150.0)]
        assert _join_wrapped_lines(lines, RIGHT_MARGIN) == ["Netease Games", "Toronto"]

    def test_three_line_wrap_is_joined_into_one(self) -> None:
        lines = [
            ("• Identified and drove the resolution of dozens of high-severity", 497.0),
            ("performance risks across project releases through backend profiling,", 496.0),
            ("improving scalability.", 200.0),
        ]
        assert len(_join_wrapped_lines(lines, RIGHT_MARGIN)) == 1

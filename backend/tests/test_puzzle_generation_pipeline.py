import pytest

from app.config import Settings
from app.errors import ApiErrorCode, AppError
from app.graph.workflow import SituationPuzzleWorkflow
from app.llm.client import FakeLlmClient
from app.models import (
    CoreTruthDraft,
    PuzzleReviewResult,
    SurfaceStoryDraft,
    TruthDraft,
)


def test_reviewer_failure_can_rewrite_surface_story_then_succeed() -> None:
    settings = Settings(puzzle_generation={"deterministic_gate_enabled": False})
    workflow = SituationPuzzleWorkflow(
        FakeLlmClient(
            surface_story_drafts=[
                SurfaceStoryDraft(
                    surface_story=(
                        "雨夜裡，男子撿到一張沒有人認領的發票。"
                        "更奇怪的是，店員突然說婚禮已經不存在。"
                    )
                ),
                SurfaceStoryDraft(
                    surface_story="雨夜裡，男子撿到一張沒有人認領的發票。隔天，他取消了婚禮。"
                ),
            ],
            review_results=[
                PuzzleReviewResult(
                    passed=False,
                    severity="major",
                    target_node="write_surface_story",
                    issues=["謎面包含兩個互不相關的異常"],
                    revision_instruction="保留 truth，只重寫成單一客觀異常。",
                ),
                PuzzleReviewResult(passed=True, target_node="finalize_puzzle"),
            ],
        ),
        settings=settings,
    )

    draft = workflow.generate_puzzle("雨夜便利商店")

    assert draft.surface_story == "雨夜裡，男子撿到一張沒有人認領的發票。隔天，他取消了婚禮。"


def test_reviewer_can_request_core_truth_regeneration() -> None:
    settings = Settings(puzzle_generation={"deterministic_gate_enabled": False})
    workflow = SituationPuzzleWorkflow(
        FakeLlmClient(
            core_truths=[
                CoreTruthDraft(
                    core_truth="男子發現店裡有秘密組織，所以取消婚禮。",
                    cause="秘密組織",
                    actor_action="男子調查秘密組織",
                    abnormal_result="取消婚禮",
                    misdirection="玩家以為只是發票。",
                ),
                FakeLlmClient.default_core_truth(),
            ],
            truth_drafts=[
                _truth("第一版真相提到秘密組織，已經偏離日常型海龜湯，因此 reviewer 要求重生核心。"),
                FakeLlmClient.default_truth_draft(),
            ],
            review_results=[
                PuzzleReviewResult(
                    passed=False,
                    severity="critical",
                    target_node="generate_core_truth",
                    issues=["核心因果過度發散"],
                    revision_instruction="改成日常誤會，不要使用秘密組織。",
                ),
                PuzzleReviewResult(passed=True, target_node="finalize_puzzle"),
            ],
        ),
        settings=settings,
    )

    draft = workflow.generate_puzzle("雨夜便利商店")

    assert "秘密組織" not in draft.truth
    assert "發票上的時間" in draft.truth


def test_deterministic_gate_rewrites_long_surface_story() -> None:
    workflow = SituationPuzzleWorkflow(
        FakeLlmClient(
            surface_story_drafts=[
                SurfaceStoryDraft(
                    surface_story=(
                        "雨夜裡，男子在便利商店撿到一張沒有人認領的發票，"
                        "他反覆比對上面的時間、品項、店名與未婚妻先前說過的每一句話，"
                        "還想起她最近提到工作室早已停用，因此感到非常不安。"
                        "他又回到店門口詢問店員，確認發票確實是在同一個晚上掉落，"
                        "並且上面的品項正好都是婚禮前不該出現的材料。"
                        "隔天，他取消了原本已經排定的婚禮。"
                    )
                ),
                SurfaceStoryDraft(
                    surface_story="雨夜裡，男子撿到一張沒有人認領的發票。隔天，他取消了婚禮。"
                ),
            ],
            review_results=[
                PuzzleReviewResult(passed=True, target_node="finalize_puzzle")
            ],
        )
    )

    draft = workflow.generate_puzzle("雨夜便利商店")

    assert len(draft.surface_story) <= 120
    assert "反覆比對" not in draft.surface_story


def test_deterministic_gate_rewrites_empty_key_facts() -> None:
    workflow = SituationPuzzleWorkflow(
        FakeLlmClient(
            key_facts_drafts=[
                FakeLlmClient.default_key_facts().model_copy(update={"key_facts": []}),
                FakeLlmClient.default_key_facts(),
            ],
            review_results=[
                PuzzleReviewResult(passed=True, target_node="finalize_puzzle")
            ],
        )
    )

    draft = workflow.generate_puzzle("雨夜便利商店")

    assert len(draft.key_facts) == 5


def test_revision_limit_returns_llm_output_invalid() -> None:
    settings = Settings(
        puzzle_generation={
            "max_revision_rounds": 0,
            "deterministic_gate_enabled": False,
        }
    )
    workflow = SituationPuzzleWorkflow(
        FakeLlmClient(
            review_results=[
                PuzzleReviewResult(
                    passed=False,
                    severity="major",
                    target_node="write_surface_story",
                    issues=["謎面不合理"],
                    revision_instruction="重寫謎面。",
                )
            ]
        ),
        settings=settings,
    )

    with pytest.raises(AppError) as exc_info:
        workflow.generate_puzzle("雨夜便利商店")

    assert exc_info.value.code == ApiErrorCode.LLM_OUTPUT_INVALID


def _truth(extra: str) -> TruthDraft:
    return TruthDraft(
        truth=(
            "男子在雨夜撿到的發票不是中獎線索，而是未婚妻當晚購物留下的收據。"
            "發票上的時間與品項和她聲稱在家準備婚禮的說法衝突，也顯示她仍在替已說停用的工作室買材料。"
            "男子隔天到店裡確認監視器，只看到未婚妻自己來付款，沒有危險或死亡事件。"
            f"{extra}他知道問題是對方長期隱瞞行蹤與金錢安排，所以決定取消婚禮。"
        )
    )

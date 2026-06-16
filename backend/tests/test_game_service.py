from app.config import StorageConfig
from app.errors import ApiErrorCode, AppError
from app.graph.workflow import SituationPuzzleWorkflow
from app.llm.client import FakeLlmClient
from app.models import Answer, QuestionJudgement, SolutionJudgement
from app.services.game_service import GameService
from app.storage import GameStorage


def make_service(tmp_path, fake_llm: FakeLlmClient) -> GameService:
    return GameService(
        workflow=SituationPuzzleWorkflow(fake_llm),
        storage=GameStorage(StorageConfig(games_dir=str(tmp_path))),
    )


def test_game_service_create_ask_unsolved_solve_and_persist(tmp_path) -> None:
    service = make_service(
        tmp_path,
        FakeLlmClient(
            question_judgements=[QuestionJudgement(is_valid_question=True, answer=Answer.YES)],
            solution_judgements=[
                SolutionJudgement(solved=False),
                SolutionJudgement(solved=True),
            ],
        ),
    )

    created = service.create_game("雨夜")
    answer = service.ask_question(created.game_id, "男子還活著嗎？")
    failed = service.submit_solution(created.game_id, "錯誤答案")
    solved = service.submit_solution(created.game_id, "正確答案")

    assert answer.display_answer == "是"
    assert failed.message == "尚未解開"
    assert failed.truth is None
    assert solved.solved is True
    assert solved.truth is not None
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_game_service_invalid_question_is_not_recorded(tmp_path) -> None:
    service = make_service(
        tmp_path,
        FakeLlmClient(
            question_judgements=[QuestionJudgement(is_valid_question=False, answer=None)]
        ),
    )
    created = service.create_game("雨夜")

    try:
        service.ask_question(created.game_id, "請給我提示")
    except AppError as exc:
        assert exc.code == ApiErrorCode.INVALID_QUESTION
    else:
        raise AssertionError("Expected invalid question error.")

    assert service.get_game(created.game_id).questions == []


def test_game_service_ended_game_rejects_more_actions(tmp_path) -> None:
    service = make_service(tmp_path, FakeLlmClient())
    created = service.create_game("雨夜")
    service.abandon_game(created.game_id)

    try:
        service.ask_question(created.game_id, "還能問嗎？")
    except AppError as exc:
        assert exc.code == ApiErrorCode.GAME_ALREADY_ENDED
    else:
        raise AssertionError("Expected ended game error.")

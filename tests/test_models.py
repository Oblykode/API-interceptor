from app.domain.models import DecisionAction, FlowStatus, RequestDecisionIn


def test_request_decision_enum_validation() -> None:
    model = RequestDecisionIn(action=DecisionAction.FORWARD, intercept_response=True)
    assert model.action == DecisionAction.FORWARD
    assert model.intercept_response is True


def test_flow_status_values() -> None:
    assert FlowStatus.PENDING_REQUEST.value == "pending_request"
    assert FlowStatus.COMPLETED.value == "completed"


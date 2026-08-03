from app.agent.intent import suggest_deterministic_tool
from app.core.schemas import ChatMessage
def test_python_compile_intent():
    s=suggest_deterministic_tool([ChatMessage(role='user',content='Projede Python sözdizimi kontrolünü çalıştır.')]); assert s.tool=='safe_terminal' and s.arguments['preset']=='python_compile'
def test_flutter_analyze_intent():
    s=suggest_deterministic_tool([ChatMessage(role='user',content='Flutter analyze çalıştır.')]); assert s.arguments['preset']=='flutter_analyze'

from pathlib import Path
from app.improvement.git_integration import SelfDevelopmentGitIntegrationStore

def test_store_is_scoped_to_supplied_root(tmp_path: Path):
    store = SelfDevelopmentGitIntegrationStore(root=tmp_path)
    assert store.root == tmp_path.resolve()

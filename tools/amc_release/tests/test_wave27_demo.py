from tools.amc_release.demo27 import exercise

def test_disposable_full_lifecycle_enforces_serving_revoke():
    result=exercise()
    assert result['publication']=='published'
    assert result['reconciliation_before']=='PASS'
    assert result['rollback']=='rolled_back'
    assert result['serving_revoked'] is True
    assert result['feedback_reopened']==1
    assert result['reconciliation_after']=='PASS'
    assert result['uat']=='BLOCK'

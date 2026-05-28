from tasks import celery_app


def test_worker_bootstrap_app_name():
    assert celery_app.main == "marketplace"

from citeguard import jobs

def test_progress_never_goes_backwards():
    mgr = jobs.JobManager(max_workers=1)
    job = mgr.create("probe.pdf")
    mgr.update(job["id"], status="running", progress=10, stage="extract")
    mgr.update(job["id"], progress=8, stage="parse")
    assert mgr.get(job["id"])["progress"] == 10
    mgr.update(job["id"], progress=42)
    assert mgr.get(job["id"])["progress"] == 42

"""arq worker entrypoint: `arq app.worker.main.WorkerSettings`.

Long-lived human approvals and multi-day negotiations are a better fit for a
durable workflow engine. Temporal is the intended future option and is not
wired in this skeleton; arq only runs short jobs.
"""

from arq.connections import RedisSettings

from app.bootstrap import register_all
from app.config import settings
from app.worker.jobs import execute_approval, index_document, resume_agent_task, run_agent_task

register_all()


class WorkerSettings:
    functions = [execute_approval, index_document, run_agent_task, resume_agent_task]
    job_timeout = 60 * 30
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

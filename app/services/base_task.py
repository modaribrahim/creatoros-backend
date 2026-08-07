import asyncio

from celery import Task


class AsyncTask(Task):
    abstract = True

    def run(self, *args, **kwargs):
        return asyncio.run(self._run(*args, **kwargs))

    async def _run(self, *args, **kwargs):
        raise NotImplementedError

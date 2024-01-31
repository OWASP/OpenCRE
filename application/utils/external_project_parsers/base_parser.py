from application.database import db
from application.cmd import cre_main
from application.defs import cre_defs as defs
from rq import Queue
from application.utils import redis
from typing import List
from application.prompt_client import prompt_client as prompt_client
import logging
import time
from alive_progress import alive_bar

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# abstract class/interface that shows how to import a project that is not cre or its core resources

class ParserInterface:
    # The name of the resource being parsed
    name: str 
    def parse(database: db.Node_collection,prompt_client: prompt_client.PromptHandler):
        """
         calls parse_project() and link_project()
        """
        raise NotImplementedError
    def link_project(database:db.Node_collection,prompt_client: prompt_client.PromptHandler):
        """
        links the resource of the project to CREs
        this can be done either using glue resources, AI or any other supported method.
        Returns a list of documents with CRE links
        """
        raise NotImplementedError

    def parse_project(database:db.Node_collection):
        """
        interface
        Parses the resources of a project, 
        returns an array of Documents with each document populated with the relevant details
        """
        raise NotImplementedError

class BaseParser():
    @classmethod
    def register_resource(self,sclass:ParserInterface,db:db.Node_collection, ph:prompt_client.PromptHandler):
        cre_main.register_standard(sclass.parse(),db,ph)

    def call_importers(self,db:db.Node_collection, prompt_handler:prompt_client.PromptHandler):
        """
        somehow finds all the importers that have been registered (either reflection for implementing classes or an explicit method that registers all available importers)
        and schedules jobs to call those importers, monitors the jobs and alerts when done same as cre_main
        """
        interface = ParserInterface()
        importers = []
        jobs = []
        conn = redis.connect()
        q = Queue(connection=conn)
        for subclass in interface.__subclasses__():
            importers.append(subclass)
            sclass = subclass()

            jobs.append(
                q.enqueue_call(
                    description=sclass.name,
                    func=BaseParser.register_resource,
                    kwargs={
                        "sclass":sclass,
                        "db": db,
                        "ph": prompt_handler,
                    },
                    timeout="10m",
                )
            )
        t0 = time.perf_counter()
        total_resources = len(jobs)
        with alive_bar(theme="classic", total=total_resources) as bar:
            while jobs:
                bar.text = f"importing {len(jobs)} standards"
                for job in jobs:
                    if job.is_finished():
                        logger.info(f"{job.description} registered successfully")
                        jobs.pop(jobs.index(job))
                    elif job.is_failed():
                        logger.fatal(
                            f"Job to register resource {job.description} failed, check logs for reason"
                        )
                    elif job.is_canceled():
                        logger.fatal(
                            f"Job to register resource {job.description} was cancelled, check logs for reason but this looks like a bug"
                        )
                    elif job.is_stopped:
                        logger.fatal(
                            f"Job to register resource {job.description} was stopped, check logs for reason but this looks like a bug"
                        )
        logger.info(
            f"imported {total_resources} standards in {time.perf_counter()-t0} seconds"
        )
        return total_resources
        # TODO(spyros): perhaps it makes sense to abstract the "schedule parser package and monitor" to another method as we're doing this twice
        # can be done by first importing everything and then calling  __subclass__() https://stackoverflow.com/questions/5881873/python-find-all-classes-which-inherit-from-this-one
  
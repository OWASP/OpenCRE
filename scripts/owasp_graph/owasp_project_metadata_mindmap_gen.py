import requests
import pydot
import os
import yaml
import sys
import base64
import time
import argparse
import json
import re
import github3
import logging
from collections import namedtuple
from pprint import pprint
from random import randint
# from github3 import GitHub
from urllib.parse import urlparse
from itertools import chain
from sqlalchemy import Column, Integer, String, create_engine, orm
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


session = requests.Session()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
Base = declarative_base()


class Info(Base):
    __tablename__ = 'info'

    name = Column(String, default='Unnamed Project', primary_key=True)
    repository = Column(String)
    level = Column(Integer, default=0)
    type = Column(String)
    pitch = Column(String)
    audience = Column(String)
    social = Column(String)
    example_usage = Column(String)
    output_type = Column(String)
    tags = Column(String)
    sdlc = Column(String)

    tags_arr = []
    sdlc_arr = []

    def __init__(self,
                 name: str,
                 repository: str,
                 level: int,
                 type: str,
                 pitch: str,
                 audience: str,
                 social: str,
                 example_usage="",
                 output_type="",
                 tags=[],
                 sdlc=[]):
        self.name = name
        self.repository = repository
        self.level = level
        self.type = type
        self.pitch = pitch
        self.audience = audience
        self.social = social
        self.example_usage = example_usage
        self.output_type = output_type

        if isinstance(tags, list):
            self.tags = ", ".join(tags)
            self.tags_arr = tags
        else:
            self.tags = tags
            if "," in tags:
                self.tags_arr = tags.split(",")
            else:
                self.tags_arr = [tags]

        if len(sdlc) == 0:
            logger.debug('sdlc 0 setting default')
            self.sdlc = "General"
            self.sdlc_arr = [self.sdlc]
        elif isinstance(sdlc, list):
            self.sdlc = ", ".join(sdlc)
            self.sdlc_arr = sdlc
        else:
            self.sdlc = sdlc
            if "," in sdlc:
                self.sdlc_arr = sdlc.split(",")
            else:
                self.sdlc_arr = [sdlc]

    @orm.reconstructor
    def init_on_load(self):
        self.tags_arr = self.tags.split(", ")
        self.sdlc_arr = self.sdlc.split(", ")


class Mindmap:
    info_arr: []
    cache: bool
    cache_file: str
    metadata_dict = {"General": [],
                     "Planning": [],
                     "Analysis": [],
                     "Design": [],
                     "Implementation": [],
                     "Maintenance": [],
                     "Strategy": [],
                     "Culture": []}

    def __init__(self, cache: bool = False, cache_file: str = None):
        self.info_arr = list()
        self.cache = cache
        self.cache_file = cache_file

        if cache:
            self.connect()
            self.load()
 
    def connect(self):
        connection = create_engine('sqlite:///'+self.cache_file, echo=False)
        Session = sessionmaker(bind=connection)
        self.session = Session()
        Base.metadata.bind = connection

        if not connection.dialect.has_table(connection, Info.__tablename__):
            Base.metadata.create_all(connection)

    def load(self):
        """ loads cache into memory 
        """
        cache = self.session.query(Info)
        for info in cache:
            for sd in info.sdlc.split(", "):
                self.metadata_dict[sd].append(info.__dict__)

    def add(self, info: Info):
        self.info_arr.append(info)
        for sd in info.sdlc_arr:
            self.metadata_dict[sd].append(info.__dict__)

        if self.cache:
            self.update_cache(info)

    def update_cache(self, info: Info):
        """

        """
        cache_entry = self.session.query(Info).filter(
            Info.name == info.name).first()
        if cache_entry is not None:
            # logger.debug("knew of %s ,updating"%cache_entry.name)
            cache_entry = info
        else:
            # logger.debug("did not know of %s ,adding"%info.name)
            self.session.add(info)

        self.session.commit()




def extract_index_meta(index: str):
    """ 
        uses regexp to extract information from index.md metadata
        arg: index:str content of idnex.md
        returns: quintuple
    """
    regexp = {'title': '(title: (?P<title>.+))',
              'tags': '(tags: (?P<tags>.+))',
              'level': '(level: (?P<level>.+))',
              'type': '(type: (?P<type>.+))',
              'pitch': ' (pitch: (?P<pitch>.+))'}
    results = {}
    metadata = re.search("---.*---", index, re.DOTALL)
    title = tags = level = type = pitch = ""
    if metadata is not None:
        for k, v in regexp.items():
            m = re.search(v, metadata.group())
            if m is not None:
                results[k] = m.group(k).strip()
            else:
                results[k] = ''
        return (results['title'],
                results['tags'],
                results['level'],
                results['type'],
                results['pitch'])
    else:
        logger.warning('failed to match header')
    logger.error("regexp bug, could not parse "+index)
    return (None, None, None, None, None)


def extract_info_meta(info: str):
    # TODO: parse info.md which is unstructured html/markdown
    return None, None, None


def extract_config_meta(config: str):
    # TODO: parse _config.yml when we start adding useful info in there
    return None


def get_project_meta(project_url: str,source_base:str)->Info:
    """ parse:
    * index.md for the string between the "---" tags in order to extract title, tags, level, type and pitch
    * info.md to extract audience, social links and code repo
    args: project_url github url to a project
    args: source_base url pointing to html version of the source
    returns: Info object
    """
    if project_url.endswith(".md"):
        logger.error("You have a bug, get_project_meta(project_url) takes a url that ends in / without the file ")
    if not project_url.endswith("/"):
        project_url = project_url + "/"
        logger.debug("added trailing slash")

    index_url = project_url + "index.md"
    index_file = session.get(index_url).json()
    index_content = base64.b64decode(index_file['content']).decode('utf-8')
    title, tags, level, type, pitch = extract_index_meta(index_content)

    info_url = project_url + "info.md"
    info_file = session.get(info_url).json()
    info_content = base64.b64decode(index_file['content']).decode('utf-8')
    audience, social, code = extract_info_meta(info_content)

    project_info = Info(name=title,
                        repository=code or source_base,
                        tags=tags,
                        level=level,
                        type=type,
                        pitch=pitch,
                        audience=audience,
                        social=social)
    return project_info


def gather_org_metadata(reponame: str, orgname: str, cache: str) -> Mindmap:
    """
        Builds the repo object for every repo in the org
        :param reponame if not None, it will search only for the specific repo
        :param orgname if not None, it will search only for the specific org
        :returns Metadata object, containing list of dicts representing the files
    """
    logger.debug("gathering metadata for "+orgname)
    result = Mindmap(cache=True, cache_file=cache)
    connection = github3.GitHub()

    query = 'filename:"info.md" path:/'
    if reponame is not None:
        search = f"repo:{reponame} {query}"
    elif orgname is not None:
        search = f"org:{orgname} {query}"
    metadata = connection.search_code(search)

    for f in metadata:
        time.sleep(1)  # throttle locally so github doesn't complain
        content = session.get(f.url)
        logger.debug("processing: "+f.url)
        if content.status_code == 200:
            resp = json.loads(content.text)
            logger.info(f"analysing data for {resp['_links']['html']}")

            if "chapter" in resp['_links']['html'].lower():  # skip chapter pages
                logger.info(resp['_links']['html'].lower() +
                      " is a chapter, skipping for now")
                continue

            # extract project base so we can get both index and info
            project_base = re.sub(
                r'\?ref=.*', "", resp['url']).replace("info.md", "")
            result.add(get_project_meta(project_base,source_base=resp['_links']['html'].replace("info.md","")))
        else:
            logger.error(f"ERROR response code: {content.status_code}")
    return result


def build_metadata(org_dict: dict, repo_dict: dict, cache: str) -> list:
    """ searches for info.yaml in the repo or the org defined
        finds the info.yaml metadata files and fetches them
        returns object representation of metadata files groupped by sdlc step
    """
    for human_org_name, github_org_name in org_dict.items():
        logger.debug("Processing %s:%s" % (human_org_name, github_org_name))
        data = gather_org_metadata(
            reponame=None, orgname=github_org_name, cache=cache)

    # TODO: when there's a use case for individual repos, uncomment
    # for human_repo_name,github_repo_name in repo_dict.items():
    #     logger.debug(f"Processing {human_repo_name}")
    #     mindmap = enhance_metadata(orgname=None,  reponame=github_repo_name,metadata=mindmap)
    return data

def add(graph, parent_node:str, child:str,**kwargs):

    if kwargs.get('url'):
        node = pydot.Node(child)
        # print('setting url %s'%kwargs.get('url'))
        node.set_URL(kwargs.get('url'))
    else:
        node = pydot.Node(child)    
    edge = pydot.Edge(parent_node, node)
    # pprint(node.get_URL())
  
    graph.add_node(node)
    graph.add_edge(edge)


def build_graph(metadata: Mindmap) -> pydot.Dot:
    graph = pydot.Dot(graph_type="graph", rankdir="LR")
    for sdlc_step, projects in metadata.metadata_dict.items():
        add(graph, parent_node="sdlc",child=sdlc_step)
        for project in projects:
            add(graph, parent_node=sdlc_step, child=project.get("name"),url=project.get('repository'))
    return graph


if __name__ == "__main__":

    # {"testOrgForMetadataScript":"testOrgForMetadataScript"} this should eventually be a yaml file or some other easily parsable file mapping repos to projects
    orgs = {"owasp": "OWASP", "zap": "zap"}
    repos = {}  # {"standaloneTestRepo1":"northdpole/standaloneTestRepo1","standaloneTestRepo2":"northdpole/standaloneTestRepo2"}

    parser = argparse.ArgumentParser(
        description='Build an owasp projects graph')
    parser.add_argument(
        '--from_cache', help='use the cache file instead of doing requests')
    args = parser.parse_args()

    if args.from_cache:
        metadata = Mindmap(cache=True, cache_file=args.from_cache)
    else:
        session.auth = (os.environ.get('GITHUB_USERNAME'),
                        os.environ.get('GITHUB_TOKEN'))
        metadata = build_metadata(
            org_dict=orgs, repo_dict=repos, cache="script_cache.sqlite")

    graph = build_graph(metadata)

    graph.write("map.dot")
    graph.write_pdf("map.pdf")
    graph.write_svg("map.svg")
    # os.stat("map.png")

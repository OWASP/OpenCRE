from github3 import GitHub
import unittest
import pydot
from owasp_project_metadata_mindmap_gen import build_graph, build_metadata,Info, gather_metadata
from tempfile import mktemp
from pprint import pprint
from unittest.mock import patch
from collections import namedtuple

class TestProjMetadataParsers(unittest.TestCase):
 
    def setUp(self):
        self.data ={'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA': [{"name": "northdpole/testRepo2",
                                                             "repository": "https://github.com/northdpole/standaloneTestRepo1",
                                                             "tags": ["defenders", "foo", "bar"],
                                                             "sdlc": ["AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "Cooking"],
                                                             "example_usage": "get hammer -> smash drives -> ignite thermite",
                                                             "output_type": ["smashed drives"]}],
 'Analysis': [{"name": "testOrg/testRepo1",
  "repository": "https://github.com/testOrgForMetadataScript/testRepo1",
   "tags": ["builders", "foo", "bar"],
    "sdlc": ["Analysis", "Implementation"],
     "example_usage": "https://demo.testOrg.testRepo1.org",
      "output_type": ["urls", "guidelines"]},
             {"name": "testOrg/testRepo2",
              "repository": "https://github.com/testOrgForMetadataScript/testRepo2",
               "tags": ["breakers", "positive", "test"],
                "sdlc": ["Analysis", "Culture"],
                 "example_usage": "docker run -v /tmp:/tmp foobar:v1.3",
                  "output_type": ["type"]}],
 'Cooking': [{"name": "northdpole/testRepo2", 
 "repository": "https://github.com/northdpole/standaloneTestRepo1", 
 "tags": ["defenders", "foo", "bar"],
  "sdlc": ["AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "Cooking"],
   "example_usage": "get hammer -> smash drives -> ignite thermite",
    "output_type": ["smashed drives"]}],
 'Culture': [{"name": "testOrg/testRepo2",
  "repository": "https://github.com/testOrgForMetadataScript/testRepo2",
   "tags": ["breakers", "positive", "test"],
    "sdlc": ["Analysis", "Culture"],
     "example_usage": "docker run -v /tmp:/tmp foobar:v1.3",
      "output_type": ["type"]}],
 'Design': [],
 'Implementation': [{"name": "testOrg/testRepo1",
  "repository": "https://github.com/testOrgForMetadataScript/testRepo1", 
  "tags": ["builders", "foo", "bar"], "sdlc": ["Analysis", "Implementation"], 
  "example_usage": "https://demo.testOrg.testRepo1.org", 
  "output_type": ["urls", "guidelines"]}],

 'Maintenance': [],
 'Planning': [],
 'Strategy': [{"name": "northdpole/standaloneTestRepo2",
  "repository": "https://github.com/northdpole/standaloneTestRepo2", 
  "tags": ["builders", "positive", "test"], 
  "sdlc": ["Strategy"],
   "example_usage": "kubectl delete po --all --all-namespaces", 
   "output_type": ["destruction"]}]}

        self.metadata = {}
        for k, vals in self.data.items():
            self.metadata[k] = []
            for v in vals:
                self.metadata[k].append(Info(v))

    def test_build_graph(self):
        self.maxDiff= None
        test_graph = build_graph(self.metadata)
        tmp_graph = mktemp()
        test_graph.write(tmp_graph)
    
        with open("test_data/map.dot") as f1, open(tmp_graph) as f2:
            graph = f1.read()
            generated_graph = f2.read()
            
        self.assertEqual(graph,generated_graph)

    @patch('owasp_project_metadata_mindmap_gen.enhance_metadata')
    def test_build_metadata(self,mocked_enhance):
        mocked_enhance.return_value = self.metadata
        org_dict = {"testOrgForMetadataScript":"testOrgForMetadataScript","owasp":"owasp", "zap":"zap"}
        repo_dict = {"standaloneTestRepo1":"northdpole/standaloneTestRepo1","standaloneTestRepo2":"northdpole/standaloneTestRepo2"}

        self.assertEqual(self.metadata, build_metadata(org_dict,repo_dict))
    
    @patch('')
    def test_get_project_meta(self,patched_github):
       pass
    
    def test_extract_index_meta(self):
        pass
        
    @unittest.skip('todo')
    def test_enhance_metadata(self):
        pass


if __name__ == '__main__':
    unittest.main()
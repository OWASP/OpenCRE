import os
import yaml
import base64
from pprint import pprint

def writeToDisk(file_title:str, cres_loc:str, file_content:str)->dict:
    with open(os.path.join(cres_loc, file_title), "w+",encoding='utf8') as fp:
        fp.write(file_content)
    return {file_title:file_content}

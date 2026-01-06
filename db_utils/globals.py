import yaml
import os
import re

project_path = re.sub(
    r"TeNNetViz.*", "TeNNetViz/", os.path.dirname(os.path.abspath(__file__))
)
os.chdir(project_path + "/db_utils")

# Load the credentials from the yaml file
yaml_file = open("credentials.yml", "r")
yaml_content = yaml.load(yaml_file, Loader=yaml.FullLoader)
yaml_file.close()

DB_URL = yaml_content["db_url"]

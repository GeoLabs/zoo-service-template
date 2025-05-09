from __future__ import annotations
from typing import Dict
import pathlib

try:
    import zoo
except ImportError:

    class ZooStub(object):
        def __init__(self):
            self.SERVICE_SUCCEEDED = 3
            self.SERVICE_FAILED = 4

        def update_status(self, conf, progress):
            print(f"Status {progress}")

        def _(self, message):
            print(f"invoked _ with {message}")

    zoo = ZooStub()

import os
import sys
import traceback
import yaml
import json
import boto3  # noqa: F401
import botocore
from loguru import logger
from urllib.parse import urlparse
from botocore.exceptions import ClientError
from botocore.client import Config
from pystac import read_file
from pystac.stac_io import DefaultStacIO, StacIO
from pystac.item_collection import ItemCollection
from zoo_calrissian_runner import ExecutionHandler, ZooCalrissianRunner
import yaml

logger.remove()
logger.add(sys.stderr, level="INFO")


class CustomStacIO(DefaultStacIO):
    """Custom STAC IO class that uses boto3 to read from S3."""

    def __init__(self):
        self.session = botocore.session.Session()
        self.s3_client = self.session.create_client(
            service_name="s3",
            region_name="us-east-1",
            endpoint_url="http://eoap-zoo-project-localstack.eoap-zoo-project.svc.cluster.local:4566",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )

    def read_text(self, source, *args, **kwargs):
        parsed = urlparse(source)
        if parsed.scheme == "s3":
            return (
                self.s3_client.get_object(Bucket=parsed.netloc, Key=parsed.path[1:])[
                    "Body"
                ]
                .read()
                .decode("utf-8")
            )
        else:
            return super().read_text(source, *args, **kwargs)

    def write_text(self, dest, txt, *args, **kwargs):
        parsed = urlparse(dest)
        if parsed.scheme == "s3":
            self.s3_client.put_object(
                Body=txt.encode("UTF-8"),
                Bucket=parsed.netloc,
                Key=parsed.path[1:],
                ContentType="application/geo+json",
            )
        else:
            super().write_text(dest, txt, *args, **kwargs)


StacIO.set_default(CustomStacIO)


class SimpleExecutionHandler(ExecutionHandler):
    def __init__(self, conf):
        super().__init__()
        self.conf = conf
        self.results = None

    def pre_execution_hook(self):
        # This method is invoked before execution starts.
        # It is used to set up the additinal parameters based on specific criteria.

        logger.info("Pre execution hook")

        #
        # Here you can patch the CWL file used for the stageout.
        #
        # For example, if you want to add a new parameter to the execution of the wrapped Application Package,
        thematic_service_name = self.get_service_for_process()
        self.conf["additional_parameters"]["thematic_service_name"] = thematic_service_name

        # In this example, you want to create a stageout.yaml file based on the service name,
        # you can first load the stageout.yaml file from the assets directory.
        stageout_yaml = yaml.safe_load(open("/assets/stageout.yaml","rb"))

        # Depending on the thematic service name, you can update the stageout.yaml file.
        # For example, if you want to import a specific Python file based on the thematic service name,
        # you can do it like this (obviously, you can also add new code to the stageout):
        entries = stageout_yaml["requirements"]["InitialWorkDirRequirement"]['listing']
        entries[0]["entry"] += "\n" +\
            "try:\n" +\
            "    import my_service_indexing\n" +\
            "except ImportError as e:\n" +\
            "    print('error loading dynamic content: '+str(e),file=sys.stderr)\n"
        #
        # In the stageout.yaml file, we have put a dedicated [INIT_TEMPLATE] string for you to replace with your code.
        # This is useful if you want to add new code to the intial phase of the stage.py file (which is the entry 0).
        # In the example below, we are adding a new variable named thematic_service_name.
        #
        entries[0]["entry"] = entries[0]["entry"].replace(
            "[INIT_TEMPLATE]",
            "thematic_service_name=sys.argv[4]\n" +
            "print(f\"thematic_service_name: {thematic_service_name}\", file=sys.stderr)"
        )
        # We are not doing it here, but you can also add new code to the stageout.yaml file.
        #
        # You can also add new Python file (or anythign else) to the stageout.yaml file.
        #
        # We can expect to have different Python files available for each thematic service name.
        #
        # We illustrate this with a simple example, only displaying an Hello string.
        #
        # In a real scenario, you should read a Python file dedicated to your thematic indexing.
        #
        # For example, if you have a file named my_service_indexing.py in the assets directory,
        # you can add it to the stageout.yaml file by adding a new entry to the listing, i.e.:
        # {
        #   "entryname": "my_service_indexing.py",
        #   "entry": open("/assets/my_service_indexing.py","rb").read().decode("utf-8")
        # }
        #
        # In this example, you should add the new my_service_indexing.py file imported at the end of the .
        #
        entries.append(
            {
                "entryname": "my_service_indexing.py",
                "entry": "import sys\n"+
                    f"print('Hello from {thematic_service_name}',file=sys.stderr)\n"+
                    "print(sys.argv,file=sys.stderr)"
            }
        )
        # You can also add new input parameters and passs it as an argument.
        stageout_yaml["inputs"]["thematic_service_name"]={"type": "string"}
        stageout_yaml["arguments"].append("$( inputs.thematic_service_name )")
        # Yet another input parameter to be passed to the wrapped Application Package.
        self.conf["additional_parameters"]["my_new_parameter"] = "my-service-name"
        #
        # We don't use it here, but you can also overwrite the environment variables available from the stageout pod.
        # i.e.:
        # stageout_yaml["requirements"]["EnvVarRequirement"]["envDef"]["AWS_ACCESS_KEY_ID"] = "XXX"
        # stageout_yaml["requirements"]["EnvVarRequirement"]["envDef"]["AWS_SECRET_ACCESS_KEY"] = "YYY"
        # stageout_yaml["requirements"]["EnvVarRequirement"]["envDef"]["AWS_REGION"] = "ZZZ"
        # You can reference an input parameter like this:
        # stageout_yaml["requirements"]["EnvVarRequirement"]["envDef"]["AWS_S3_ENDPOINT"] = "$( inputs.endpoint_url )"
        #
        # Or add new ones:
        # stageout_yaml["requirements"]["EnvVarRequirement"]["envDef"]["MY_NEW_ENV_VAR"] = "$( inputs.my_new_env_var )"
        #
        # Here we store the stageout.yaml file in the tmpPath directory.
        #
        self.stageout_file_path = f"/{self.conf['main']['tmpPath']}/stageout{self.conf['lenv']['usid']}.yaml"
        stageout_file=open(self.stageout_file_path,"w")
        yaml.dump(stageout_yaml,stageout_file)
        stageout_file.close()
        #
        # Below we set the stageout.yaml file to be used to wrap the Application Package.
        #
        os.environ["WRAPPER_STAGE_OUT"] = self.stageout_file_path
        #
        # You can imagine having a dedicated stageout.yaml file for each thematic service name also.
        # Then you can use the following:
        # os.environ["WRAPPER_STAGE_OUT"] = f"/myPathToStageOuts/mystageOut{themactic_service_name}.yaml"
        #

    def post_execution_hook(self, log, output, usage_report, tool_logs):
        # This method is invoked after execution ends.
        # It is used to handle the output files of the execution.

        logger.info("Post execution hook")
        os.remove(self.stageout_file_path)

        return

    def get_pod_env_vars(self):
        # This method is used to set environment variables for the pod
        # spawned by calrissian.

        logger.info("get_pod_env_vars")

        env_vars = {"A": "1", "B": "2"}

        return env_vars

    def get_pod_node_selector(self):
        # This method is used to set node selectors for the pod
        # spawned by calrissian.

        logger.info("get_pod_node_selector")

        node_selector = {}

        return node_selector

    def get_service_for_process(self):
        # This method is used to set the service name based on the process name.
        processes_relationship = {
            "my-service-name1": [
                "process-name1",
                "process-name2",
            ],
            "my-service-name2": [
                "process-name3",
                "process-name4",
            ],
        }
        for i in processes_relationship:
            if self.conf["lenv"]["Identifier"] in processes_relationship[i]:
                return i
        return "my-service-name"


    def get_additional_parameters(self):
        # sets the additional parameters for the execution
        # of the wrapped Application Package

        logger.info("get_additional_parameters")
        additional_parameters: Dict[str, str] = {}
        additional_parameters = self.conf.get("additional_parameters", {})

        additional_parameters["sub_path"] = self.conf["lenv"]["usid"]

        #
        # From here you can overwrite the default additional parameters depending on the service.
        # You can also add new additional parameters to the execution of the wrapped Application Package, like the service name.
        #
        # For example, if you want to add a new parameter to the execution of the wrapped Application Package,
        # you can do it like this:
        #
        # additional_parameters["service_name"] = "MyServiceName"
        # additional_parameters["thematic_service_name"] = "MyServiceName"
        #
        # If you want to overwrite an existing parameter, you can do it like this:
        #
        # additional_parameters["sub_path"] = "MyComputedPath"
        #
        # From your stageout.cwl, you can access the additional parameters.
        #
        # Here we will mimic selecting the service name based on the process name.
        #
        # additional_parameters["thematic_service_name"] = get_service_for_process(self)
        # Here we wil finally set the service name based on the process identifier.
        # additional_parameters["thematic_service_name"] = self.conf["lenv"]["Identifier"]
        #

        logger.info(f"additional_parameters: {additional_parameters.keys()}")

        return additional_parameters

    def handle_outputs(self, log, output, usage_report, tool_logs):
        """
        Handle the output files of the execution.

        :param log: The application log file of the execution.
        :param output: The output file of the execution.
        :param usage_report: The metrics file.
        :param tool_logs: A list of paths to individual workflow step logs.

        """

        try:
            logger.info("handle_outputs")
            if output is not None:
                logger.info(f"Set output to {output['s3_catalog_output']}")
                self.results = {"url": output["s3_catalog_output"]}

            self.conf["main"]["tmpUrl"] = self.conf["main"]["tmpUrl"].replace(
                "temp/", self.conf["auth_env"]["user"] + "/temp/"
            )
            services_logs = [
                {
                    "url": os.path.join(
                        self.conf["main"]["tmpUrl"],
                        f"{self.conf['lenv']['Identifier']}-{self.conf['lenv']['usid']}",
                        os.path.basename(tool_log),
                    ),
                    "title": f"Tool log {os.path.basename(tool_log)}",
                    "rel": "related",
                }
                for tool_log in tool_logs
            ]
            cindex=0
            if "service_logs" in self.conf:
                cindex=1
            for i in range(len(services_logs)):
                okeys = ["url", "title", "rel"]
                keys = ["url", "title", "rel"]
                if cindex > 0:
                    for j in range(len(keys)):
                        keys[j] = keys[j] + "_" + str(cindex)
                if "service_logs" not in self.conf:
                    self.conf["service_logs"] = {}
                for j in range(len(keys)):
                    self.conf["service_logs"][keys[j]] = services_logs[i][okeys[j]]
                cindex += 1
                logger.warning(f"service_logs: {self.conf['service_logs']}")

            self.conf["service_logs"]["length"] = str(cindex)
            logger.info(f"service_logs: {self.conf['service_logs']}")

        except Exception as e:
            logger.error("ERROR in handle_outputs...")
            logger.error(traceback.format_exc())
            raise (e)

    def get_secrets(self):
        # This method is used to set the secrets for the pods
        # spawned by calrissian.
        return {}


def {{cookiecutter.workflow_id |replace("-", "_")  }}(conf, inputs, outputs):  # noqa

    try:
        with open(
            os.path.join(
                pathlib.Path(os.path.realpath(__file__)).parent.absolute(),
                "app-package.cwl",
            ),
            "r",
        ) as stream:
            cwl = yaml.safe_load(stream)

        execution_handler = SimpleExecutionHandler(conf=conf)

        runner = ZooCalrissianRunner(
            cwl=cwl,
            conf=conf,
            inputs=inputs,
            outputs=outputs,
            execution_handler=execution_handler,
        )

        working_dir = os.path.join(conf["main"]["tmpPath"], runner.get_namespace_name())
        os.makedirs(
            working_dir,
            mode=0o777,
            exist_ok=True,
        )
        os.chdir(working_dir)

        exit_status = runner.execute()

        if exit_status == zoo.SERVICE_SUCCEEDED:
            logger.info(f"Setting Collection into output key {list(outputs.keys())[0]}")
            outputs[list(outputs.keys())[0]]["value"] = json.dumps(
                execution_handler.results, indent=2
            )
            return zoo.SERVICE_SUCCEEDED

        else:
            conf["lenv"]["message"] = zoo._("Execution failed")
            logger.error("Execution failed")
            return zoo.SERVICE_FAILED

    except Exception as e:

        logger.error("ERROR in processing execution template...")
        logger.error("Try to fetch the tool logs if any...")

        try:
            # TODO: Why does this job log not fetched in case of success?
            with open(os.path.join(
                conf["main"]["tmpPath"], 
                runner.get_namespace_name(),
                "job.log"),
                "w",
                encoding="utf-8") as file:
                file.write(runner.execution.get_log())
            len=1
            if "service_logs" not in conf:
                conf["service_logs"] = {}
            else:
                len=int(conf["service_logs"]["length"])
            keys=["url","title","rel"]
            if "length" in conf["service_logs"]:
                for i in range(len(keys)):
                    keys[i]+="_"+str(int(conf["service_logs"]["length"]))
            conf["service_logs"][keys[0]]=os.path.join(
                conf['main']['tmpUrl'].replace(
                    "temp/",conf["auth_env"]["user"]+"/temp/"
                ),
                runner.get_namespace_name(),
                "job.log"
            )
            conf["service_logs"][keys[1]]="Job pod log"
            conf["service_logs"][keys[2]]="related"
            conf["service_logs"]["length"]=str(len+1)
            logger.info("Job log saved")
        except Exception as e:
            logger.error(f"{str(e)}")

        try:
            tool_logs = runner.execution.get_tool_logs()
            execution_handler.handle_outputs(None, None, None, tool_logs)
        except Exception as e:
            logger.error(f"Fetching tool logs failed! ({str(e)})")

        stack = traceback.format_exc()

        logger.error(stack)

        conf["lenv"]["message"] = zoo._(f"Exception during execution...\n{stack}\n")

        return zoo.SERVICE_FAILED

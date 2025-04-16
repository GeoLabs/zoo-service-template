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

        logger.info("Pre execution hook")

    def post_execution_hook(self, log, output, usage_report, tool_logs):

        # unset HTTP proxy or else the S3 client will use it and fail
        os.environ.pop("HTTP_PROXY", None)

        logger.info("Post execution hook")

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

    def get_additional_parameters(self):
        # sets the additional parameters for the execution
        # of the wrapped Application Package

        logger.info("get_additional_parameters")

        additional_parameters = {
            "s3_bucket": "results",
            "sub_path": self.conf["lenv"]["usid"],
            "region_name": "us-east-1",
            "aws_secret_access_key": "test",
            "aws_access_key_id": "test",
            "endpoint_url": "http://eoap-zoo-project-localstack.eoap-zoo-project.svc.cluster.local:4566",
        }

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

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
from loguru import logger
from pystac import read_file, Collection, Catalog
from pystac.item_collection import ItemCollection
from pystac.stac_io import StacIO
from zoo_calrissian_runner import ZooCalrissianRunner
from zoo_template_common import CommonExecutionHandler, CustomStacIO


logger.remove()
logger.add(sys.stderr, level="INFO")

StacIO.set_default(CustomStacIO)


class SimpleExecutionHandler(CommonExecutionHandler):
    """Simple execution handler for basic ZOO workflows.
    
    Extends CommonExecutionHandler with specific storage platform configuration.
    """

    def __init__(self, conf, outputs):
        super().__init__(conf, outputs)

    def get_additional_parameters(self) -> Dict[str, str]:
        """Get additional parameters with eoap storage platform."""
        additional_parameters = super().get_additional_parameters()
        additional_parameters["storage_platform"] = "eoap"
        return additional_parameters


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

        execution_handler = SimpleExecutionHandler(conf=conf, outputs=outputs)

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
            for i in outputs:
                logger.info(f"Setting Collection into output key {i}: {outputs[i]}")
                if "collection" in outputs[i]:
                    outputs[i]["value"] = json.dumps(
                        outputs[i]["collection"], indent=2
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

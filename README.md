# zoo-service-template

ZOO Project template for deploying Application Packages

This template can be used with the skaffold from the branch of this [repository]().

It demonstrates how you can:
 * dynamically update the input parameters passed to the wrapped EOAP by updating the `additional_parameters` section of the main configuration dictionary from the `pre_execution_hook`,
 * dynamically insert new code to the initialization phaze in the `stage.py` file from the `stageout.yaml`,
 * dynamically add a new Python file to the `stageout.yaml`,
 * dynamically set any, or override predefined environment variables,
 * update or override the stageout.yaml at runtime.




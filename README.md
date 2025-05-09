# zoo-service-template

ZOO Project template for deploying Application Packages

This template can be used with the skaffold from the branch `axis3-skaffold` of this [repository](https://github.com/GeoLabs/ZOO-Project).

It demonstrates how you can:
 * dynamically update the input parameters passed to the wrapped EOAP by updating the `additional_parameters` section of the main configuration dictionary from the `pre_execution_hook`,
 * dynamically insert new code to the initialization phaze in the `stage.py` file from the `stageout.yaml`,
 * dynamically add a new Python file to the `stageout.yaml`,
 * dynamically set any, or override predefined environment variables,
 * update or override the stageout.yaml at runtime.

To setup the solution, please use the commands below.

````
git clone -b axis3-skaffold https://github.com/GeoLabs/ZOO-Project.git
cd ZOO-Project
skaffold dev
````

Once deployed, you can access your server instance throught SwaggerUI from there: http://localhost:8080/swagger-ui/oapip/#/.

You can use the following [CWL](https://raw.githubusercontent.com/EOEPCA/deployment-guide/main/scripts/processing/oapip/examples/convert-url-app.cwl) and change the workflow id from `convert-url` to one of the following: `process-name1`, `process-name2`, `process-name3`, `process-name4`. 

To do so from the command line, you can use the following.

`````
for i in $(seq 4); do
    curl -o test.cwl https://raw.githubusercontent.com/EOEPCA/deployment-guide/main/scripts/processing/oapip/examples/convert-url-app.cwl
    sed "s:convert-url:process-name$i:g" -i test.cwl
    curl -X 'POST'\
        "http://localhost:8080/anonymous/ogc-api/processes?w=process-name$i" \
        -H 'accept: application/json' \
        -H "Content-Type: application/cwl+yaml" \
        --data-binary @test.cwl
done
`````


Then to exeute tasks, proceed as shown below.

````
curl -X "POST"\
    -v \
    'http://localhost:8080/anonymous/ogc-api/processes/process-name1/execution' \
    -H 'accept: /*' \
    -H 'Prefer: respond-async;return=representation' \
    -H 'Content-Type: application/json' \
    -d '{
        "inputs": {
            "fn": "resize",
            "url":  "https://eoepca.org/media_portal/images/logo6_med.original.png",
            "size": "50%"
        }
    }'
````

Grab the `Location` header returned, i.e. `< Location: http://localhost:8080/anonymous/ogc-api/jobs/3601c992-2cdf-11f0-9743-2e7049224aa9`.

````
curl http://localhost:8080/anonymous/ogc-api/jobs/3601c992-2cdf-11f0-9743-2e7049224aa9
````

Once the job is completed, you can see the stageout log messages using the link entitled "Tool log node_stage_out.log".

Here is an example of the resulting messages.

````
2025-05-09T14:10:18.473662Z - node-stage-out-pod-yuykqogw - thematic_service_name: my-service-name1
cat_url: /var/lib/cwl/stgda0686b7-7a85-4ce0-a5f3-664e20ad5644/bhlkle3w
2025-05-09T14:10:18.473752Z - node-stage-out-pod-yuykqogw - bucket: results
subfolder: 3601c992-2cdf-11f0-9743-2e7049224aa9
2025-05-09T14:10:18.523768Z - node-stage-out-pod-yuykqogw - upload /tmp/catalog/logo6_med.original-resize.png to s3://results/3601c992-2cdf-11f0-9743-2e7049224aa9/3601c992-2cdf-11f0-9743-2e7049224aa9/logo6_med.original-resize-1746799816.914262048/logo6_med.original-resize.png
2025-05-09T14:10:18.544014Z - node-stage-out-pod-yuykqogw - upload logo6_med.original-resize-1746799816.914262048 to s3://results/3601c992-2cdf-11f0-9743-2e7049224aa9
2025-05-09T14:10:18.610079Z - node-stage-out-pod-yuykqogw - upload collection.json to s3://results/3601c992-2cdf-11f0-9743-2e7049224aa9
2025-05-09T14:10:18.668969Z - node-stage-out-pod-yuykqogw - upload catalog.json to s3://results/3601c992-2cdf-11f0-9743-2e7049224aa9
2025-05-09T14:10:18.723500Z - node-stage-out-pod-yuykqogw - Hello from my-service-name1
['stage.py', '/var/lib/cwl/stgda0686b7-7a85-4ce0-a5f3-664e20ad5644/bhlkle3w', 'results', '3601c992-2cdf-11f0-9743-2e7049224aa9', 'my-service-name1']
s3://results/3601c992-2cdf-11f0-9743-2e7049224aa9/catalog.json
````








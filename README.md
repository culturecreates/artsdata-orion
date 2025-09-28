# artsdata-orion

A constellation of stars. In other words, a collection of websites loaded into Artsdata by Culture Creates using only the JSON-LD published on each website. 

For websites loaded by CAPACOA visit [artsdata-stewards/artsdata-orion](https://github.com/artsdata-stewards/artsdata-orion/tree/main/.github/workflows).

This repo uses the [artsdata-pipeline-action](https://github.com/culturecreates/artsdata-pipeline-action?tab=readme-ov-file#artsdata-pipeline-action) to crawls websites and push to Artsdata.

Each website loaded using the code in this repo creates an artifact that is added to the Artsdata Databus and loaded into a graph in Artsdsata.

To create custom data pipelines or collaborate on an individual data source with others outside of Culture Creates, please create separate repos called artsdata-planet-[NAME].
# artsdata-orion

A constellation of stars. In other words, a collection of websites loaded into Artsdata by Culture Creates using only the JSON-LD published on each website. 

Each websites loaded using the code in this repo created an artifact. All artifacts are in the group http://kg.artsdata.ca/databus/culture-creates/artsdata-orion

To create custom data pipelines or collaborate on an individual data source with others outside of Culture Creates, please create separate repos called artsdata-planet-[NAME].

### Parameters

Note: These parameters are the same as those for all Orion JSON-LD pipelines. You can reuse the same `page-url`, CSS `entity-identifier`, `is-paginated` and `headless` parameters from the [Artsdata JSON-LD Event Score workflows](https://github.com/culturecreates/artsdata-score/blob/main/README.md).

- [artifact] Domain of the website, with a dash in lieu of the dot before the top-level domain. For example: `imperialtheatre-ca`.
- [page-url] URL of the webpage listing all events
- [entity-identifier ] CSS selector to identify individual event webpage URLS. 
- [downloadFile] Enter any file name with extension `.jsonld`. Please include the domain of the website. For example: `imperialtheatre-ca-events.jsonld`.
- [is-paginated] Is the page paginated? Enter true or false.
- [headless] Run in headless mode to capture JSON-LD injected by javascript.  Enter true or false.

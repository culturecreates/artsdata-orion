# artsdata-orion

A constellation of stars. In other words, a collection of websites loaded into Artsdata by Culture Creates using only the JSON-LD published on each website. 

Each websites loaded using the code in this repo created an artifact. All artifacts are in the group http://kg.artsdata.ca/databus/culture-creates/artsdata-orion

To create custom data pipelines or collaborate on an individual data source with others outside of Culture Creates, please create separate repos called artsdata-planet-[NAME].

### Parameters
Note: These parameters are the same as those for all Orion JSON-LD pipelines. You can reuse the same `page-url`, CSS `entity-identifier`, `is-paginated` and `headless` parameters from the [Artsdata JSON-LD Event Score workflows](https://github.com/culturecreates/artsdata-score/blob/main/README.md).
- [page-url] URL of the webpage listing all events
- [entity-identifier ] CSS selector to identify individual event webpage URLS. 
- File name. Enter any file name with extension `.csv`. Please include the domain of the website. For example: `sandersoncentre-ca_report.csv`
- [is-paginated] Is the page paginated? Enter true or false.
- [headless] Run in headless mode to capture JSON-LD injected by javascript.  Enter true or false.
  
<img width="388" alt="Screenshot 2025-02-14 at 12 46 35 PM" src="https://github.com/user-attachments/assets/64ffed13-d03c-4d51-8d1f-48ee632443e2" />

require 'ferrum'
require 'json'
require 'linkeddata'

module HeadlessBrowser
  def self.fetch_json_ld_objects(entity_urls, base_url)
    browser = Ferrum::Browser.new(headless: true, pending_connection_errors: false)
    graph = RDF::Graph.new
    entity_urls.each do |entity_url|
      begin
        browser.go_to(entity_url)
        sleep 15
        browser.stop
        json_ld_scripts = browser.css("script[type='application/ld+json']")
        json_ld_scripts.each do |script|
          begin
            graph << JSON::LD::API.toRdf(JSON.parse(script.text))
          rescue JSON::ParserError => e
            puts "Error parsing JSON-LD: #{e.message}"
          end
        end
      rescue StandardError => e
        puts "Error processing #{entity_url} in headless mode: #{e.message}"
      end
    end
    sparql_paths = [
      "./sparql/replace_blank_nodes.sparql",
      "./sparql/fix_entity_type_capital.sparql",
      "./sparql/fix_date_timezone.sparql"
    ]

    SparqlProcessor.perform_sparql_transformations(graph, sparql_paths, base_url)
    graph
  end
end

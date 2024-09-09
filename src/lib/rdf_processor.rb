require 'linkeddata'
require 'sparql'
require_relative 'sparql_processor'
module RDFProcessor
  def self.process_rdf(entity_urls, base_url)
    graph = RDF::Graph.new
    add_url_sparql_file = File.read('./sparql/add_derived_from.sparql')

    entity_urls.each do |entity_url|
      begin
        puts "Processing #{entity_url} in non-headless mode"
        entity_url = entity_url.gsub(' ', '+')
        loaded_graph = RDF::Graph.load(entity_url)
        sparql_file_with_url = add_url_sparql_file.gsub("subject_url", entity_url)
        loaded_graph.query(SPARQL.parse(sparql_file_with_url, update: true))
        graph << loaded_graph
      rescue StandardError => e
        puts "Error loading RDF from #{entity_url}: #{e.message}"
      end
    end

    sparql_paths = [
      "./sparql/replace_blank_nodes.sparql",
      "./sparql/fix_entity_type_capital.sparql",
      "./sparql/fix_date_timezone.sparql",
      "./sparql/fix_address_country_name.sparql",
      "./sparql/remove_objects.sparql"
    ]

    SparqlProcessor.perform_sparql_transformations(graph, sparql_paths, base_url)
  end

  private

  def self.perform_sparql_transformations(graph, sparql_paths, base_url)
    sparql_paths.each do |sparql_path|
      file = File.read(sparql_path).gsub("domain_name", base_url)
      graph.query(SPARQL.parse(file, update: true))
    end
    graph
  end
end

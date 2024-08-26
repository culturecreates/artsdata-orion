module SparqlProcessor
  def self.perform_sparql_transformations(graph, sparql_paths, base_url)
    sparql_paths.each do |sparql_path|
      file = File.read(sparql_path).gsub("domain_name", base_url)
      graph.query(SPARQL.parse(file, update: true))
    end
    graph
  end
end


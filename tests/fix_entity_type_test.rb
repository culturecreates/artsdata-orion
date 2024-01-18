require 'minitest/autorun'
require 'linkeddata'

class SparqlTest < Minitest::Test

  # Load and parse sparql
  def setup
    @fix_entity_type_sparql_file = "./sparql/fix_entity_type.sparql"
    @replace_blank_node_sparql_file = "./sparql/replace_blank_nodes.sparql"
  end

  # check that the blank node is replaced
  def test_capitalized_first_letter
    sparql = SPARQL.parse(File.read(@fix_entity_type_sparql_file), update: true)
    graph = RDF::Graph.load("./tests/fixtures/test_capital_types.jsonld")
    # puts "before: #{graph.dump(:jsonld)}"
    graph.query(sparql)
    # puts "after: #{graph.dump(:jsonld)}"
    assert_equal [
      RDF::URI("http://schema.org/Person"),
      RDF::URI("http://schema.org/Place")
    ], graph.query([nil, RDF::type, nil]).each.objects
  end

  # check that the blank node is replaced
  def test_blank_node_replaced
    sparql = SPARQL.parse(File.read(@replace_blank_node_sparql_file), update: true)
    graph = RDF::Graph.load("./tests/fixtures/test_blank_nodes.jsonld")
    # puts "before: #{graph.dump(:jsonld)}"
    graph.query(sparql)
    # puts "after: #{graph.dump(:jsonld)}"
    assert_equal false, graph.query([nil, RDF::type, RDF::URI("http://schema.org/Thing")]).each.subjects.node?
  end
end

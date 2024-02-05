require 'minitest/autorun'
require 'linkeddata'

class FixEntityTypeCapitalTest < Minitest::Test

  def setup
    @fix_entity_type_sparql_file = "./sparql/fix_entity_type_capital.sparql"
  end

  # check that the type object is fixed
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
end

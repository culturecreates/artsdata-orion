require 'minitest/autorun'
require 'linkeddata'

class RemoveObjectTest < Minitest::Test
  def setup
    @remove_object_sparql_file = "./sparql/remove_objects.sparql"
  end

  def test_remove_object
    sparql = SPARQL.parse(File.read(@remove_object_sparql_file), update: true)
    graph = RDF::Graph.load("./tests/fixtures/test_remove_object.jsonld")
    
    # puts "before: #{graph.dump(:jsonld)}"
    graph.query(sparql)
    
    # puts "after: #{graph.dump(:jsonld)}"
    assert_equal(0, graph.count, "The graph should have no objects after the SPARQL update.")
  end
  

end
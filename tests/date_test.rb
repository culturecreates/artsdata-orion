require 'minitest/autorun'
require 'linkeddata'

class DateTest < Minitest::Test

  def setup
    fix_date_sparql_file = './sparql/fix_date.sparql'
    @sparql = SPARQL.parse(File.read(fix_date_sparql_file), update: true)
  end

  # check that the dates are correctly formatted
  def test_date_format
    graph = RDF::Graph.load("./tests/fixtures/test_date.jsonld")
    # puts "before: #{graph.dump(:jsonld)}"
    graph.query(@sparql)
    # puts "after: #{graph.dump(:jsonld)}"
    dates = graph.query([nil, RDF::Vocab::SCHEMA.startDate, nil]).each.objects
    dates.each do |start_date|
      assert_match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-\d{2}:\d{2}\s*$/, start_date.to_s)
    end
  end

  def test_date_type
    graph = RDF::Graph.load("./tests/fixtures/test_date_types.jsonld")
    # puts "before: #{graph.dump(:jsonld)}"
    graph.query(@sparql)
    # puts "after: #{graph.dump(:jsonld)}"
    events = JSON.parse(graph.dump(:jsonld))
    events.each do |event|
      start_date = event['http://schema.org/startDate']
      assert_equal(start_date[0]["@type"], "http://schema.org/Date")
    end
  end

  # Check that startDate retains its data type after being fixed
  def test_date_type_in_context
    graph = RDF::Graph.load("./tests/fixtures/test_date_type_in_context.jsonld")
    # get the startDate data type before fixing
    expected = graph.query([nil, RDF::Vocab::SCHEMA.startDate, nil]).first.object.datatype
    graph.query(@sparql)
    assert_equal expected, graph.query([nil, RDF::Vocab::SCHEMA.startDate, nil]).first.object.datatype, 
      "Data type of startDate should be preserved after fixing"
  end
end

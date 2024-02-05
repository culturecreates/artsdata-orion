require 'minitest/autorun'
require 'linkeddata'

class FixDateTimezoneTest < Minitest::Test

  def setup
    fix_date_timezone_sparql_file = './sparql/fix_date_timezone.sparql'
    @sparql = SPARQL.parse(File.read(fix_date_timezone_sparql_file), update: true)
  end

  # Check that date timezone is fixed and retains data type
  def test_fix_timezone
    graph = RDF::Graph.load("./tests/fixtures/test_date_timezone_fix.jsonld")
    graph.query(@sparql)

    # Test event1
    expected =  RDF::Literal.new('2024-02-03T20:00:00-07:00', datatype: RDF::URI("http://schema.org/Date"))
    actual = graph.query([RDF::URI('http://example.com/event1'), RDF::Vocab::SCHEMA.startDate, nil]).first.object
    assert_equal expected, actual, "event1 failed"
      
    # Test event2
    expected =  RDF::Literal.new('2024-02-03T20:00:00-07:00', datatype: RDF::URI("http://schema.org/DateTime"))
    actual = graph.query([RDF::URI('http://example.com/event2'), RDF::Vocab::SCHEMA.startDate, nil]).first.object
    assert_equal expected, actual, "event2 failed"
  
    # Test event3
    expected =  RDF::Literal.new('2024-02-03T20:00:00-07:00', datatype: RDF::URI("http://schema.org/Date"))
    actual = graph.query([RDF::URI('http://example.com/event3'), RDF::Vocab::SCHEMA.startDate, nil]).first.object
    assert_equal expected, actual, "event3 failed"

    # Test event4
    expected =  RDF::Literal.new('2024-02-03T20:00:00-07:00', datatype: RDF::URI("http://schema.org/Date"))
    actual = graph.query([RDF::URI('http://example.com/event4'), RDF::Vocab::SCHEMA.endDate, nil]).first.object
    assert_equal expected, actual, "event4 failed"
  end
end

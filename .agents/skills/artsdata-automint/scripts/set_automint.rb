# Turns Artsdata auto-minting on or off for one or more data feed graphs.
#
# This script holds no SPARQL of its own. It calls nebula's
# ArtifactController#toggle_auto_minting, so it always runs whatever update
# nebula currently uses. It runs against production GraphDB with the
# credential in nebula's encrypted Rails credentials. Run it with nebula's
# `rails runner`:
#
#   cd ~/repos/culturecreates/nebula
#   bin/rails runner <path>/set_automint.rb true <graph-uri> [<graph-uri> ...]
#
# First argument is "true" (turn on) or "false" (turn off).
#
# If nebula renames or reshapes the action, this script stops with an error
# instead of guessing: read app/controllers/artifact_controller.rb and update
# the call below.

value = ARGV.shift
graphs = ARGV
unless %w[true false].include?(value) && graphs.any?
  abort "Usage: bin/rails runner set_automint.rb true|false <graph-uri> [<graph-uri> ...]"
end
graphs.each do |graph|
  abort "Not an Artsdata graph URI: #{graph}" unless graph.match?(%r{\Ahttp://kg\.artsdata\.ca/[\w.~\-/]+\z})
end

unless ArtifactController.method_defined?(:toggle_auto_minting) && ArtifactController.method_defined?(:get_automint_status)
  abort "nebula's ArtifactController no longer has toggle_auto_minting / get_automint_status. " \
        "Read app/controllers/artifact_controller.rb and update this script."
end

Rails.application.config.graph_api_endpoint = "https://db.artsdata.ca"
abort "No graph_db_basic_auth in nebula credentials" if Rails.application.credentials.graph_db_basic_auth.blank?

failed = false
graphs.each do |graph|
  # Call the action directly (skipping the web login filter) with a stand-in request.
  controller = ArtifactController.new
  controller.request = ActionDispatch::TestRequest.create
  controller.response = ActionDispatch::TestResponse.new
  controller.params = ActionController::Parameters.new(graph: graph, new_boolean: value)
  controller.toggle_auto_minting

  if controller.flash.alert.present?
    failed = true
    puts "FAILED #{graph}: #{controller.flash.alert}"
    next
  end

  # Read the flag back with nebula's own reader to confirm the result.
  status = controller.get_automint_status(graph)
  if status.to_s == value
    puts "automint=#{value}: #{graph} (#{controller.flash.notice})"
  else
    failed = true
    puts "FAILED #{graph}: nebula reported '#{controller.flash.notice}' but the flag reads #{status}"
  end
end
exit(1) if failed

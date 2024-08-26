require 'ferrum'
require 'json'

module HeadlessBrowser
  def self.fetch_json_ld_objects(entity_urls)
    browser = Ferrum::Browser.new(headless: true, pending_connection_errors: false)
    json_ld_objects = []

    entity_urls.each do |entity_url|
      begin
        browser.go_to(entity_url)
        browser.network.wait_for_idle(duration: 1, timeout: 60.0)
        json_ld_scripts = browser.css("script[type='application/ld+json']")
        json_ld_scripts.each do |script|
          begin
            json_ld_objects << JSON.parse(script.text)
          rescue JSON::ParserError => e
            puts "Error parsing JSON-LD: #{e.message}"
          end
        end
      rescue StandardError => e
        puts "Error processing #{entity_url} in headless mode: #{e.message}"
      end
    end

    json_ld_objects
  end
end

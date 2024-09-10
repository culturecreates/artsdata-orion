require 'nokogiri'
require 'open-uri'

module EntityFetcher
  def self.fetch_entity_urls(page_url, entity_identifier, is_paginated)
    base_url = page_url.split('/')[0..2].join('/')
    entity_urls = []

    if is_paginated == 'false'
      page_number = nil
    elsif is_paginated == 'true'
      page_number = 1
    else
      page_number = is_paginated.to_i
    end
    
    max_retries, retry_count = 3, 0

    loop do
      url = "#{page_url}#{page_number}"
      puts "Fetching entity urls from #{url}..."
      begin
        main_page_html_text = URI.open(url).read
      rescue StandardError => e
        retry_count += 1
        if retry_count < max_retries
          retry
        else
          puts "Max retries reached. Unable to fetch the content for page #{page_number}."
          break
        end
      end

      main_doc = Nokogiri::HTML(main_page_html_text)
      entities_data = main_doc.css(entity_identifier)
      number_of_entities = entity_urls.length
      entities_data.each do |entity|
        href = entity["href"]
        entity_urls << (href.start_with?('http') ? href : base_url + href)
      end

      break if entity_urls.length == number_of_entities || page_number.nil?

      page_number += 1
      retry_count = 0
    end

    entity_urls.uniq
  end
end

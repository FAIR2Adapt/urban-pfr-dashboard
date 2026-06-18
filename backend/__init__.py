"""Backend package for the flood-risk dashboard. 
  - config        : reads the data-source registry (config/sources.json)
  - adapters      : pluggable data-source resolvers (one per source type)
  - services      : geo/flood/metadata processing 
  - api.routes    : maps HTTP paths to adapters and returns normalized datasets
  - app           : the HTTP server + static file serving for the frontend
"""

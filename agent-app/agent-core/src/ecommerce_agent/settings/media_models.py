"""Image and video model selection.

Change IMAGE_MODEL and VIDEO_MODEL here when switching models. API keys must
stay in .env and must never be committed to source control.
"""

# Volcengine Ark may require an inference endpoint ID (ep-...) here instead of
# the public model family name shown in its catalog.
IMAGE_MODEL = "replace-with-seedream-model-or-endpoint-id"
VIDEO_MODEL = "replace-with-seedance-model-or-endpoint-id"

# These clients currently implement the Volcengine Ark Seedream/Seedance
# protocols. A model using a different provider protocol needs a client adapter.
IMAGE_BACKEND = "api"
VIDEO_BACKEND = "api"

IMAGE_API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
VIDEO_CREATE_URL = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
VIDEO_QUERY_URL = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"

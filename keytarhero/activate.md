# First time on a new machine (after git clone)
cd keytarhero
docker build -t keytarhero .
docker run -d --name keytarhero -p 8080:8080 keytarhero
# Open http://localhost:8080

# Stop the container
docker stop keytarhero

# Start it again later
docker start keytarhero

# Or run a fresh one
docker run -d --name keytarhero -p 8080:8080 keytarhero

# Rebuild after code changes
docker build -t keytarhero .
docker rm -f keytarhero
docker run -d --name keytarhero -p 8080:8080 keytarhero

# IMPORTANT: Make sure .dockerignore exists in the repo.
# Without it, local node_modules leak into the build and break it.
# The Dockerfile has a safety fallback (re-runs npm ci after COPY)
# but .dockerignore saves ~130MB of transfer time.
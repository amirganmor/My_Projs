# Stop the container
docker stop keytarhero

# Start it again later
docker start keytarhero

# Or run a fresh one
docker run -d --name keytarhero -p 8080:8080 keytarhero

# Rebuild after code changes
cd ~/venv/keytarhero
docker build -t keytarhero .
docker rm -f keytarhero
docker run -d --name keytarhero -p 8080:8080 keytarhero
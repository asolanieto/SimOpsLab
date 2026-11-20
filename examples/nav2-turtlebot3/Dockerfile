FROM ghcr.io/ros-navigation/nav2_docker:lyrical-1.5.3-standard@sha256:22d126afac99a8cf20600756b64196fcbe04fefabbe53851efa946377d83362c

# The official image omits this runtime dependency required by nav2_map_server.
# Pin both the Ubuntu archive snapshot and package version.
ARG APT_SNAPSHOT=20261119T000000Z
RUN apt-get update --snapshot "${APT_SNAPSHOT}" \
    && apt-get install --yes --snapshot "${APT_SNAPSHOT}" --no-install-recommends \
       libgraphicsmagick++-q16-12t64=1.4+really1.3.46-2 \
    && rm -rf /var/lib/apt/lists/*

LABEL org.opencontainers.image.title="SimOps Nav2 TurtleBot3 demo"
LABEL org.opencontainers.image.base.name="ghcr.io/ros-navigation/nav2_docker:lyrical-1.5.3-standard"

FROM public.ecr.aws/docker/library/rust:1.85.1-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends strace && rm -rf /var/lib/apt/lists/*

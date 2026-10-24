FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# This Python app does not use Yarn. Its stale apt signing key blocks SSH setup.
RUN rm -f /etc/apt/sources.list.d/yarn.list

FROM node:22-alpine

RUN corepack enable && corepack prepare pnpm@10.5.2 --activate

WORKDIR /workspace

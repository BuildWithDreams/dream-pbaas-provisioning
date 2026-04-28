#!/bin/bash
docker ps --filter 'name=vrsctest' --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
docker logs dev200-vrsctest-1 --tail 30 2>&1

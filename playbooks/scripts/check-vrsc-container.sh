#!/bin/bash
docker ps --filter 'name=vrsc' --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
docker logs vrsc --tail 30 2>&1

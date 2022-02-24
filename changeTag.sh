#!/bin/bash

sed "s/tagVersion/$1/g" pgw-canary.yaml > canary-rollout.yml

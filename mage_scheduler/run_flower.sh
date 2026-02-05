#!/bin/bash

# Run Flower monitoring UI for Celery

flower --broker=redis://localhost:6379/0 --port=5555

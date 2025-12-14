#!/bin/bash
cd /Users/christopher.messer/PycharmProjects/versiful_backend
mv backend/lambdas lambdas
rmdir backend 2>/dev/null || true
rm -rf frontend 2>/dev/null || true
echo "Directories reorganized successfully"


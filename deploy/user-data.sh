#!/bin/bash
set -euxo pipefail
dnf -y update
dnf -y install docker amazon-ssm-agent
systemctl enable --now docker
systemctl enable --now amazon-ssm-agent
usermod -aG docker ec2-user
# The application container is started by deploy_ec2.sh over SSM; this script only
# prepares the host, so a re-deploy never needs a new instance.

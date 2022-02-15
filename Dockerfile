FROM ubuntu:20.04
MAINTAINER Lee Roder "lee.roder@bluevolt.com"
RUN DEBIAN_FRONTEND=noninteractive apt-get update 
RUN DEBIAN_FRONTEND=noninteractive apt-get -y install apt-utils
RUN DEBIAN_FRONTEND=noninteractive apt-get -y upgrade
RUN DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade
RUN DEBIAN_FRONTEND=noninteractive apt-get -yq install net-tools 
RUN DEBIAN_FRONTEND=noninteractive apt-get -yq install iputils-ping 
RUN DEBIAN_FRONTEND=noninteractive apt-get -yq install dnsutils 
RUN DEBIAN_FRONTEND=noninteractive apt-get -yq install vim 
RUN DEBIAN_FRONTEND=noninteractive apt-get -yq install python3-pip python-is-python3 
RUN DEBIAN_FRONTEND=noninteractive apt-get -yq install python3-venv 
RUN DEBIAN_FRONTEND=noninteractive apt-get -yq install git
RUN DEBIAN_FRONTEND=noninteractive apt-get -yq install cmake 
RUN DEBIAN_FRONTEND=noninteractive apt-get -yq install libssl-dev
RUN DEBIAN_FRONTEND=noninteractive apt-get -yq install supervisor
RUN useradd -ms /bin/bash bvadmin
COPY config/etc/supervisord.conf /etc/supervisord.conf
COPY microservice/main.py /home/bvadmin
COPY microservice/schema.py /home/bvadmin
RUN mkdir /home/bvadmin/gateways
COPY microservice/gateways/*.py /home/bvadmin/gateways
RUN chown bvadmin:bvadmin /home/bvadmin/main.py
RUN su - bvadmin -c "cd /home/bvadmin && python3 -m venv venv"
RUN su - bvadmin -c "cd /home/bvadmin && source venv/bin/activate && pip3 install wheel"
RUN su - bvadmin -c "cd /home/bvadmin && source venv/bin/activate && pip3 install uvicorn[standard] fastapi payload-api"
EXPOSE 8082
ENTRYPOINT ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]

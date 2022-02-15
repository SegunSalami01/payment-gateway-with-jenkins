# PaymentGateway

## Overview

This README covers the following items:

- Adding New Gateways
- Repository Layout
- Docker Containerization
- Container Registries
- Kubernetes Deployment

## Adding New Gateways

### Background

Historically, payment gateway support was embedded in the monolith, and adding a payment gateway included adding database tables to the BlueVolt database as well as making changes to the BT Admin UI and adding code in the monolith to support a new payment gateway

When the decision was make to implement new payment gateways outside the monolith, one of the key design goals was to require as little change to the monolith as possible when adding a new payment gateway.

After examining existing code and database structure, it was determined that by a one-time addition of two new tables (MicroservicePaymentGatewayAccountType and MicroservicePaymentGatewayAccount), along with a one-time change to the legacy code to support this new 'dynamic model', new payment gateways could be added to the system by simply INSERTing a new record into the table MicroservicePaymentGatewayAccountType. 

### Overview

Adding a support for a new payment gateway is achieved at a high level by simply:

1.  Adding a record to the MicroservicePaymentGatewayAccountType that essentially lists the set of required keywords to display in the UI for that payment gateway when prompting a user to enter their credentials for that particular payment gateway time (e.g. 'Login' and 'Password' or 'APIKey'), and 
2. Creating a new payment gateway class in the PaymentGateway repository, in folder microserver/gateways.

### Implementation

In preparation for adding a new payment gateway, what needs to be determined initially is what core metadata a given payment gateway system requires for authentication/authorization and how is provided support for all methods required by the BlueVolt platform.  Presently, the platform supports two methods - simple payment (immediate, in full payment) via credit card and full refund processing.

#### This research phase consists of:

1. Read all necessary documentation for the new payment gateway to gain an understanding on what will be required for the new payment gateway.
2. Identify set of authentication credentials (e.g. 'Login' and 'Password')
3. Determine if the payment gateway provider maintains a python library for interaction with their system or if they support some generic https POST/PATCH style interface directly
4. Document the methods that will be utilized to support the BlueVolt platform (per above, simple credit card payment and full refund).
5. Outline database record that will need to be added to table MicroservicePaymentGatewayAccountType

Once the research is complete, there are two steps: Add record to MicroservicePaymentGatewayAccountType and add a python class with a standardized set of methods to the PaymentGateway repository.

#### Add record to MicroservicePaymentGatewayAccountType

The dbo.MicroservicePaymentGateayType table stores the gateway name, type id, and "Field" names that correspond accordingly to the "Value" columns in the dbo.MicroservicePaymentGateway table. Note, there are also "DisplayOrder" columns that define the order in which fields will be displayed in the BT Admin UI.  Up to seven (7) fields can be specified when adding a payment gateway, along with the name of that payment gateway.  Examples include:

`INSERT INTO MicroservicePaymentGatewayAccountType(PaymentGatewayAccountName, Field1, DisplayOrder1, Field2, DisplayOrder2)  VALUES ('Payload', 'ApiKey', 1, 'ProcessingId', 2)`

`INSERT INTO MicroservicePaymentGatewayAccountType(PaymentGatewayAccountName, Field1, DisplayOrder1, Field2, DisplayOrder2)  VALUES ('CardConnect', 'Login', 1, 'Password', 2)`

Of course, the proper means for adding a row would be via a database migration.   In order to add a new Payment Gateway API gateway type to the database, the migration file must insert a new row into the dbo.MicroservicePaymentGatewayType table.  Make sure that the migration handles the case where the record is already added to the table to allow for production database to be updated without running the migration script.

#### Implement new Payment Gateway class

1. Adhere to existing conventions in the API.  Namely, each class must be completely contained in its own python file and public methods must EXACTLY MATCH: process_payment() and process_refund().  Further, any metadata required by a payment gateway shall be added in the form of an environment variable read by main.py and passed as a parameter when calling the class (for example, CardConnect expects all calls to hit a specific url and since they provide no 3rd party libraries, our code must be written to pass this url in such that changing it does not require a code change).
2. Add new python class to the gateways folder with two methods: process_payment() and process_refund().  Note that presently, since process_payment is a 'simple credit card' payment-in-full method, many payment gateway systems support a single-step 'payment amount authorization' PLUS 'payment' API call.
3. Extend main.py to recognize the new gateway type.  This must be added toward the beginning of EACH supported API call in main.py (e.g. paymentGatewa/processPayment and paymentGateway/processRefund).
4. Make any/all necessary changes to the underlying schema in schema.py.  For example, the GatewayType Enum will need to be extended, as will the GatewayCredentials enum, at a minimum.
5. Add new python class file to folder microservices/gateways
6. If any additional 3rd party libraries are required, these must be tested and then added to the python venv in the Dockerfile.  Specifically, there is a line that would need to be extended:

`RUN su - bvadmin -c "cd /home/bvadmin && source venv/bin/activate && pip3 install uvicorn[standard] fastapi payload-api"`

Please reference documents/BlueVoltPaymentGatewayAPISpecV1.md for further API specific information.

## Repository Layout

There are essentially two components in this repo.   One is the actual code, and the other is any/all necessary configuration data required to construct a Docker container and inject it into a Kubernetes cluster.

The code must all live in the microservice folder (with subfolders as needed).  The configuration data must all live in the config folder (with subfolders as needed).

## Docker Containerization

This overview assumes that you already have docker installed.  Refer to other publications for that:

Windows: https://docs.docker.com/docker-for-windows/install/

Linux: https://docs.docker.com/engine/install/ubuntu/

MacOS: https://docs.docker.com/docker-for-mac/install/

With docker installed, there are two steps to containerization - building and running.

### Building a Docker Container

To create a container, one must have a Dockerfile.   This file can have any name you wish, and there are multitudes of ideas and conversations surrounding that.   The net of it all is if you are sitting in a folder that has a file named Dockerfile and run a 'docker build...' command, it finds and uses that file by default.  To specify a file with a different name or in a different folder, the '-f' option must be included.

The Dockerfile itself is basically a list of instructions or directives for Docker.  Docker supports a set of directive 'keywords'.  Basic directives include FROM, RUN, COPY, EXPOSE, ENTRYPOINT.  FROM tells docker which base image you wish to start your container build from (typically some sort of Linux OS image).   RUN allows you to execute a series of commands in this new container.   Typically it is used to apply updates and install any necessary packages that might be needed.  It can be used for other things too, such as setting up a python venv, running pip install, etc.   COPY allows you to copy files into your container - for example, your python code!  EXPOSE allows you to tell docker which port(s) this containers will be listening on internally.   FInally, ENTRYPOINT is what you want the container to DO when it is run.   Typically, that's to run your code in a way that ensures it is being monitored and kept running by the base OS you selected.

To build the docker container for the PaymentGateway microservice for local use, from a command prompt and sitting in the top level directory for this repository:

`cd config`

`docker build --rm=true --force-rm=true --no-cache -t paymentgateway:<major version>.<minor-version>.<point-release> .`

Where major version, minor version, point release are numerical.   The first build should be 0.0.1.  Discussions surrounding when to revise that build number, implications to container deployment into repositories, and implication to tagging are outside the scope of this document.

Briefly, the --rm, --force-rm, --no-cache are great 'beginner' settings for a Docker build.  As you get more advanced and understand what's going on under the hood (intermediate containers, incremental edits to docker files, temporary suspension of ENTRYPOINT directive in order to get a shell in your container for debug purposes), you may decide to relax/remove some of those options. 

The -t option is important - that's the 'tag' that will be associated with the 'container' once it is built.

To see a list of containers on your local system:

`docker container ls`

For a high-level overview of Docker containers, refer to:  https://www.docker.com/resources/what-container

For a deeper dive, refer to: https://docs.docker.com/get-started/#what-is-a-container

At this point, what you should feel great comfort in is that, upon successful completion of a 'docker build...' command, you will have a container that can be 'activated' or 'run' whenever you wish!

### Running a Docker Container

Running a docker container is very straightforward really.   It can be as simple as:

`docker run paymentgateway:0.0.1`

Of course, recognize that there could be MANY things your container must know about.  For example, which external port you might wish to route traffic through to reach the internal port you are listening on, in the case of a web back end server.   Another example is that you may not wish to embed connection strings or logins/passwords or secrets into your container (all excellent decisions!).  Briefly, here is a more detailed 'docker run...' example:

docker run -i -t -p 8000:8080 --add-host logger.bluevolt.local:104.210.57.146 --add-host cache.bluevolt.local:40.118.164.96 --env CACHE_USER=myuser --env CACHE_SECRET=mypassword --rm paymentgateway:0.0.1 /bin/bash

A quick breakdown of those options:

-i means keep STDIN open even if not attached.  -t means attach a pseudo-tty.  If you intend to run a container with an interactive shell open (more on that in a bit), those two options are very important.  -p describes a source and destination port, if desired.  In the example above, this tells docker on your local computer to listen on port 8000 (you must not have anything else running on your system that is already 'bound' to that port) and route that traffic to port 8080 in the container.  --add-host is effectively a way to pump in /etc/hosts entries in order to route domain names in your code to actual IP addresses in the outside world.  --env allows you to pass in environment variables which can be referenced by your code.  --rm ensures that the image is removed when execution is terminated.  The /bin/bash at the end would fire up your container and plop you into a bash shell if you needed to do some debugging.  Note that there are some limitations/special requirements for this last bit.

To see a list of images on your local system:

`docker image ls`

Note that over time, the number of containers and images on your local system can and will proliferate!   It is up to you to prune and manage those.   Fortunately, docker has many commands to assist with that.  Probably the single most comprehensive command is:

`docker system prune`

Here is a link with more details: https://docs.docker.com/engine/reference/commandline/system_prune/

## Container Registries

At some point, you are ready to take the next step and have your container become more generally accessible.   This is where docker container repositories come in.  One that many folks have heard of is dockerhub.   Indeed this is where many OS images are available, including Ubuntu 20.04 Server.  There are many others, however, both public and private.  

The 'docker pull' command allows us to retrieve containers from repositories which we have access to.  You might now be thinking 'well, I don't want our code to be publicly accessible'.   That's right!  We will want a place that our PaymentGateway containers can be stored which is available internally.  In BlueVolt's case, since our AKS clusters (Azure Kubernetes Server - in other words, a Kubernetes aka k8s cluster), are in Azure, it makes a lot of sense to have Docker repositories there.  And we do!

The steps to get a docker container published to/updated in a container repository are something like:

`docker login bvdevdocker.azurecr.io`
`docker tag paymentgateway:0.0.1 bvdevdocker.azurecr.io/dev/paymentgateway:0.0.1`
`docker push bvdevdocker.azurecr.io/dev/paymentgateway:0.0.1`

The first command authenticates you with and connects you to a BlueVolt container registry in Azure.   The second generates a tag for the container in question.  The third command pushes your local container to the repository.  This is a very important step in CI/CD and Kubernetes deployment (see below).  Note that versioning is very important and useful (touched on below).   Also note that if you push a tagged version of a container that happens to already exist in the repository, docker does a compare and only updates/changes the parts of a container that have actually changed (if any).

## Docker for Initial Deployment

Successfully build and run a container based on: https://github.com/bluevolt-tech/PaymentGateway/blob/offshore_dev/Dockerfile

## Kubernetes Deployment

https://bluevoltllc.sharepoint.com/:f:/r/sites/BlueVoltAllTeam/Shared%20Documents/Engineering/DevOps/Microservices/Payment%20Gateway%20k8s%20config%20files?csf=1&web=1&e=megTGM
# payment-gateway-with-jenkins

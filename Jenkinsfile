pipeline {

  environment {
    dockerimagename = "bvdevdocker.azurecr.io/dev/payment-gateway"
    dockerImage = ""
    NAMESPACE = getNamespace()
    DOCKER_TAG = getDockerTag()
  }

  agent any

  stages {

    stage('Checkout Source') {
      steps {
        git 'https://github.com/SegunSalami01/payment-gateway-with-jenkins.git'
      }
    }

 
    stage('Build image') {
      steps{
        script {
          dockerImage = docker.build dockerimagename
           dockerImage.tag("${DOCKER_TAG}")
        }
      }
    }
    
    stage('Pushing Image') {
      environment {
               registryCredential = 'acr_credentials'
           }
      steps{
        script {
          docker.withRegistry( 'https://bvdevdocker.azurecr.io', registryCredential ) {
            dockerImage.push("${DOCKER_TAG}")
          }
        }
      }
    }

    stage('Deploy to k8s'){
      steps{
        sh "chmod +x changeTag.sh"
        sh "./changeTag.sh ${DOCKER_TAG}"
        sshagent(['automation-machine']) {
          sh "scp -o StrictHostKeyChecking=no canary-rollout.yml kustomization.yaml ingress.yaml secret.yaml service-active.yaml service-preview.yaml namespace.yaml bvadmin@52.158.245.71:/home/bvadmin"
          script{
            try{
              sh "ssh bvadmin@52.158.245.71 kubectl apply -k ."
            }
            catch(error){
              sh "ssh bvadmin@52.158.245.71 kubectl create -k ."
            }
          }
        }
      }
    }
    
    



  }

}

def getDockerTag(){
  def props = readProperties file: 'config.toml'
   def DOCKER_TAG = props['DOCKER_VERSION']
  return DOCKER_TAG
}

def getNamespace(){
  def props = readProperties file: 'config.toml'
  def NAMESPACE = props['NAMESPACE']
  return NAMESPACE
}

## About the Project
This is a finished Python implementation of the ([deprecated][deprecation-url]) codecrafters 
["Build Your Own Docker" Challenge][build-your-own-docker-url]. This code can pull an image from 
[Docker Hub](https://hub.docker.com/) and run a command under process and filesystem isolation.

## Running the Code
This code uses linux-specific syscalls so will be run _inside_ a Docker container.

Please ensure you have [Docker installed](https://docs.docker.com/get-docker/)
locally.

Next, add a [shell alias](https://shapeshed.com/unix-alias/):

```sh
alias mydocker='docker build -t mydocker . && docker run --cap-add="SYS_ADMIN" mydocker'
```

(The `--cap-add="SYS_ADMIN"` flag is required to create
[PID Namespaces](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html))

You can now execute the code and run a simple command like this:

```sh
mydocker run alpine:latest cat /etc/issue
```

## Demo video
Here's a video of the code being run in the codecrafters test environment.

https://github.com/user-attachments/assets/1ae8adb3-13d9-418f-9182-e41dd0dcb01e

[build-your-own-docker-url]: https://codecrafters.io/challenges/docker
[deprecation-url]: https://forum.codecrafters.io/t/docker-challenge-is-deprecated/626

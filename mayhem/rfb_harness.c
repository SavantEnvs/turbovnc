/*
 * Fuzz harness for the TurboVNC server (Xvnc): replaces the stock main() of
 * unix/Xvnc/programs/Xserver/dix/stubmain.c, which is left out of the link.
 *
 * The input file is one RFB client byte stream. It is delivered to the real, whole server
 * (dix_main -> TurboVNC's rfbserver.c / auth / encoders / websockets) through `-inetd`, which
 * needs a real TCP socket on stdin: the harness builds a loopback pair, forks a pump that
 * writes the input and drains the server's replies, and runs the server on the other end. The
 * server exits when the client side closes, so every execution is one complete session.
 */
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

extern char **environ;
int dix_main(int argc, char *argv[], char *envp[]);

#define MAX_INPUT (1 << 20)

static void pump(int fd, const unsigned char *buf, size_t len)
{
  char sink[65536];
  size_t off = 0;

  signal(SIGPIPE, SIG_IGN);
  while (off < len) {
    ssize_t n = write(fd, buf + off, len - off);
    if (n < 0) {
      if (errno == EINTR) continue;
      break;
    }
    off += (size_t)n;
  }
  shutdown(fd, SHUT_WR);
  while (read(fd, sink, sizeof(sink)) > 0)
    ;
  _exit(0);
}

int main(int argc, char **argv)
{
  static const char *server_args[] = {
    "Xvnc", "-inetd", "-nolock", "-nolisten", "tcp", "-nolisten", "local",
    "-securitytypes", "none", "-geometry", "320x240", "-depth", "24", "-ac", NULL
  };
  unsigned char *buf;
  size_t len = 0;
  FILE *f;
  int lst, cli, srv;
  struct sockaddr_in addr;
  socklen_t alen = sizeof(addr);
  char *args[32];
  int nargs = 0;
  pid_t pid;

  if (argc < 2) {
    fprintf(stderr, "usage: %s <rfb-client-stream-file> [extra Xvnc args]\n", argv[0]);
    return 2;
  }
  if (!(f = fopen(argv[1], "rb"))) {
    perror(argv[1]);
    return 2;
  }
  if (!(buf = malloc(MAX_INPUT))) return 2;
  len = fread(buf, 1, MAX_INPUT, f);
  fclose(f);

  memset(&addr, 0, sizeof(addr));
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if ((lst = socket(AF_INET, SOCK_STREAM, 0)) < 0 ||
      bind(lst, (struct sockaddr *)&addr, sizeof(addr)) < 0 || listen(lst, 1) < 0 ||
      getsockname(lst, (struct sockaddr *)&addr, &alen) < 0 ||
      (cli = socket(AF_INET, SOCK_STREAM, 0)) < 0 ||
      connect(cli, (struct sockaddr *)&addr, sizeof(addr)) < 0 ||
      (srv = accept(lst, NULL, NULL)) < 0) {
    perror("loopback socket pair");
    return 2;
  }
  close(lst);

  if ((pid = fork()) < 0) return 2;
  if (pid == 0) {
    close(srv);
    pump(cli, buf, len);
  }
  close(cli);
  free(buf);
  dup2(srv, 0);
  dup2(srv, 1);
  if (srv > 1) close(srv);

  /* The server edits some option strings in place, so they must not be literals. */
  for (const char **a = server_args; *a; a++) args[nargs++] = strdup(*a);
  for (int i = 2; i < argc && nargs < 31; i++) args[nargs++] = argv[i];
  args[nargs] = NULL;
  return dix_main(nargs, args, environ);
}

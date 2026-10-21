#!/usr/bin/env perl
# watchdog.pl SECS COMMAND [ARG...]: run COMMAND with a wall-clock limit.
#
# A plain `perl -e 'alarm N; exec ...'` does not stop the docker CLI: it is
# a Go program and ignores SIGALRM. This one keeps watching from its own
# process. At SECS it sends TERM to COMMAND and every process below it
# (docker CLI, node, bash, and their children), then KILL 3 s later to any
# that are left. It exits with COMMAND's status (128 + signal when a signal
# ended it), or 124 after a timeout, with a line on stderr.
#
# It cannot reach a process inside a container: killing a `docker exec` CLI
# leaves the exec'd process running, so callers also run `timeout` in the
# container, and stop a named `docker run` container after a 124.
use strict;
use warnings;
use POSIX ();
use Time::HiRes qw(sleep time);

my ($secs, @cmd) = @ARGV;
die "usage: watchdog.pl SECS COMMAND [ARG...]\n" unless defined $secs && $secs =~ /^\d+$/ && $secs > 0 && @cmd;

my $pid = fork() // die "watchdog.pl: fork: $!\n";
if ($pid == 0) {
  { no warnings "exec"; exec { $cmd[0] } @cmd; }
  print STDERR "watchdog.pl: exec $cmd[0]: $!\n";
  POSIX::_exit(127);
}

# The exit status the caller sees for a finished COMMAND.
sub status { my $s = shift; ($s & 127) ? 128 + ($s & 127) : $s >> 8 }

# wait_for SECONDS -> COMMAND's raw wait status, or undef if it still runs.
sub wait_for {
  my $end = time + shift;
  while (1) {
    return $? if waitpid($pid, POSIX::WNOHANG()) == $pid;
    return undef if time >= $end;
    sleep 0.1;
  }
}

# tree -> COMMAND's pid and every descendant's, parents first.
sub tree {
  my %kids;
  for (`ps -A -o pid= -o ppid=`) {
    my ($p, $pp) = split;
    push @{ $kids{$pp} }, $p if defined $pp;
  }
  my @all = ($pid);
  for (my $i = 0; $i < @all; $i++) { push @all, @{ $kids{ $all[$i] } // [] } }
  return @all;
}

my $s = wait_for($secs);
exit status($s) if defined $s;

my @term = tree();
kill 'TERM', @term;
$s = wait_for(3);
my @kill;
if (!defined $s) {
  my %seen;
  @kill = grep { !$seen{$_}++ && kill(0, $_) } @term, tree();
  kill 'KILL', @kill;
  waitpid($pid, 0);
}
printf STDERR "watchdog.pl: %s reached the %d s limit; TERM to %s%s\n", $cmd[0], $secs, join(',', @term),
  @kill ? '; KILL 3 s later to ' . join(',', @kill) : '';
exit 124;

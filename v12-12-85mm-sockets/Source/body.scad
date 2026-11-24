// All dimensions in mm. Export with -D 'part="red-base"' or 'part="white-inlay"'.
$fn = 96;
part = "red-base";
socket_diameter = 12.85;
socket_depth = 15.5;
socket_chamfer = .6;

module rounded_plate(length, width, height, radius) {
    hull()
        for (x = [-1, 1], y = [-1, 1])
            translate([x*(length/2-radius), y*(width/2-radius), 0])
                cylinder(r=radius, h=height);
}

module plinth() {
    length = 188;
    width = 46;
    height = 9;
    chamfer = 1.25;
    corner = 4;
    slice = .01;
    union() {
        hull() {
            rounded_plate(length-2*chamfer, width-2*chamfer, slice, corner-chamfer);
            translate([0,0,chamfer]) rounded_plate(length, width, slice, corner);
        }
        translate([0,0,chamfer])
            rounded_plate(length, width, height-2*chamfer, corner);
        hull() {
            translate([0,0,height-chamfer-slice])
                rounded_plate(length, width, slice, corner);
            translate([0,0,height-slice])
                rounded_plate(length-2*chamfer, width-2*chamfer, slice, corner-chamfer);
        }
        translate([0,-19.8,8.5]) rounded_plate(49, 3.6, 33.5, 1.2);
    }
}

// Recess and matching insert share the same nominal boundary.
module panel() {
    hull()
        for (x = [-19,19], z = [-12,12])
            translate([x,z]) circle(2.5);
}

module crest() {
    scale([.56,.56]) import("crest-red.svg", center=true);
}

module at_front() {
    translate([0,-21.6,26.4]) rotate([90,0,0]) children();
}

module red_base() {
    union() {
        difference() {
            plinth();
            at_front() translate([0,0,-1.2]) linear_extrude(1.22) panel();
        }
        at_front() translate([0,0,-1.24]) linear_extrude(1.24) crest();
    }
}

module white_inlay() {
    at_front() translate([0,0,-1.2]) linear_extrude(1.2)
        difference() {
            panel();
            crest();
        }
}

module fit_coupon() {
    height = 18;
    extension = .05;
    difference() {
        hull()
            for (x = [-34,34], y = [-8,8])
                translate([x,y,0]) cylinder(r=3,h=height);
        translate([-37,-11,-.1]) cube([5,4,height+.2]);
        for (i = [0:3]) {
            diameter = socket_diameter+.2*(i-2);
            x = -28.5+19*i;
            translate([x,0,height-socket_depth])
                cylinder(d=diameter,h=socket_depth+extension);
            translate([x,0,height-socket_chamfer])
                cylinder(d1=diameter,d2=diameter+2*(socket_chamfer+extension),
                         h=socket_chamfer+extension);
        }
    }
}

if (part == "red-base") red_base();
if (part == "white-inlay") white_inlay();
if (part == "fit-coupon") fit_coupon();

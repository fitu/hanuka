// All dimensions in mm. Export with -D 'part="red-base"' or 'part="white-inlay"'.
$fn = 96;
part = "red-base";
socket_diameter = 13.6;
socket_depth = 10.4;

module rounded_plate(length, width, height, radius) {
    hull()
        for (x = [-1, 1], y = [-1, 1])
            translate([x*(length/2-radius), y*(width/2-radius), 0])
                cylinder(r=radius, h=height);
}

module plinth() {
    union() {
        rounded_plate(200, 50, 6, 5);
        hull() {
            translate([0,0,5.99]) rounded_plate(200, 50, .01, 5);
            translate([0,0,9]) rounded_plate(194, 44, .01, 4);
        }
        translate([0,0,9]) rounded_plate(194, 44, 41, 4);
    }
}

// Recess and matching insert share the same nominal boundary.
module panel() {
    hull()
        for (x = [-20,20], z = [-17,17])
            translate([x,z]) circle(2.5);
}

module crest() {
    scale([.75,.75]) import("crest-red.svg", center=true);
}

module at_front() {
    translate([0,-22,29.5]) rotate([90,0,0]) children();
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
    difference() {
        hull()
            for (x = [-34,34], y = [-8,8])
                translate([x,y,0]) cylinder(r=3,h=12);
        for (i = [0:3])
            translate([-28.5+19*i,0,12-socket_depth])
                cylinder(d=socket_diameter+(.6*(i-2)),h=socket_depth+.1);
    }
}

if (part == "red-base") red_base();
if (part == "white-inlay") white_inlay();
if (part == "fit-coupon") fit_coupon();
